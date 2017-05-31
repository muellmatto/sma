#!/usr/bin/env python3

from configparser import ConfigParser
from datetime import datetime
from io import BytesIO
from os import remove
from os.path import dirname, join, realpath
from sys import exit

import flask
import notmuch


SMA_PATH = dirname(realpath(__file__))

SMA_CONFIG_PATH = join( SMA_PATH, 'sma.conf')

db = None

app = flask.Flask(__name__)


# -----------------------------------------------------
# read config 
# -----------------------------------------------------

try:
    sma_config = ConfigParser()
    sma_config.read(SMA_CONFIG_PATH)
    ADMIN = sma_config['SMA']['admin']
    PASSWORD = sma_config['SMA']['password']
    SMA_PORT = int(sma_config['SMA']['port'])
    MAILDIR = sma_config['SMA']['maildir']
    app.secret_key = sma_config['SMA']['secret']
except:
    print('please check configfile: ', SMA_CONFIG_PATH)
    exit(1)



### notmuch handling

def smaSearch(q):
    #with notmuch.Database(path = '/home/matto/Workspace/data/maildirs') as db:
    db = notmuch.Database(path = '/home/matto/Workspace/data/maildirs') 
    query = notmuch.Query(db, q)
    query.set_sort(notmuch.Query.SORT.NEWEST_FIRST)
    msgs = query.search_messages()
    msglist = list(msgs)[:100]
    # db.close()
    return msglist
    # This is dirty! We are NOT closing the database .... o.0


def mailList(smaQuery):
    search = smaSearch(smaQuery)
    mails = [
                {
                    'filename': x.get_filename(), 
                    'date': datetime.fromtimestamp(int(x.get_date())).strftime('%Y-%m-%d %H:%M:%S'),
                    'id': x.get_message_id(),
                    'subject': x.get_header('Subject'),
                    'from': x.get_header('From'),
                    'to': x.get_header('To')
                } 
                for x in search]
    return mails


def buildMailMap(ID):
    search = smaSearch('id:' + str(ID))
    if len(search) == 0:
        return 'something went wrong!'
    mail = search[0]
    try:
        mailMeta = [ 
                        {
                            'type': x.get_content_type(),
                            'charset': x.get_content_charset(),
                            'disposition': x.get_content_disposition(),
                            'filename': x.get_filename()
                        }
                        for x in mail.get_message_parts()]
        parts = [ 
                        {
                            'meta': mailMeta[i],
                            'data': mail.get_part(i+1)
                        } 
                        if mailMeta[i]['type'].startswith('text') else 
                        {
                            'meta': mailMeta[i],
                        } 
                        for i in range(len(mailMeta)) 
                    ]
    except:
        with open(mail.get_filename(), 'rb') as rawMail:
            rawData = rawMail.read()
        parts = [
                    {
                        'meta':
                                {
                                    'filename': None,
                                    'disposition': None,
                                    'charset': 'utf-8',
                                    'type': 'text/plain'
                                },
                                'data': rawData
                    }
                ]
    mailMap = {
                'subject': mail.get_header('subject'),
                'parts' : parts 
            }
    return mailMap


def getAttachment(ID, filename):
    search = smaSearch('id:' + str(ID))
    mail = search[0]
    filenames = [ x.get_filename() for x in mail.get_message_parts() ]
    return mail.get_part( filenames.index(filename) +1) 



### routes

# favicon
@app.route('/favicon.ico')
def favicon():
    return flask.send_from_directory(join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


# list of mails or search 
@app.route('/', methods=['GET', 'POST'])
def sma():
    if not 'username' in flask.session:
        return 'You are not logged in <br><a href="' + flask.url_for('login') + '">login</a>'
    if flask.request.method == 'GET':
        return flask.render_template("search.html")
    elif flask.request.method == 'POST':
        smaQuery = flask.request.form['query']
        for prefix in ['subject', 'from', 'to', 'attachment']:
            if not flask.request.form[prefix] =='':
                smaQuery += ' AND ' + prefix + ':' + flask.request.form[prefix]
        if flask.request.form['dateFrom'] != '' or flask.request.form['dateTo'] != '':
            smaQuery += ' AND date:' + flask.request.form['dateFrom'] + '..' + flask.request.form['dateTo']
        if smaQuery.startswith(' AND'):
            smaQuery = smaQuery[5:]
        print(smaQuery)
        mails = mailList(smaQuery)
        return flask.render_template("list.html", mails=mails)


# delete an email
@app.route('/delete', methods=['GET', 'POST'])
def delete():
    if flask.request.method == 'POST':
        with notmuch.Database(path = '/home/matto/Workspace/data/maildirs' , mode=1) as db_rw:
            for mailId in flask.request.form:
                for filename in smaSearch('id:' + mailId)[0].get_filenames():
                    print(filename)
                    db_rw.remove_message(filename)
                    remove(filename)
    return flask.redirect(flask.url_for('sma'))


# login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == 'POST':
        user_name = flask.request.form['username']
        user_password = flask.request.form['password']
        if user_name == ADMIN and user_password == PASSWORD:
            flask.session.permanent = True
            flask.session['username'] = user_name
            # print('logged in')
            return flask.redirect(flask.url_for('sma'))
    return '''
        <form action="" method="post">
            <p><input type=text name=username>
            <p><input type=password name=password>
            <p><input type=submit value=Login>
        </form>
    '''


# logout 
@app.route('/logout')
def logout():
    # remove the username from the session if it's there
    flask.session.pop('username', None)
    return flask.redirect(flask.url_for('sma'))


## view an email
@app.route('/<ID>')
def showMail(ID):
    if not 'username' in flask.session:
        return 'You are not logged in <br><a href="' + flask.url_for('login') + '">login</a>'
    mailMap = buildMailMap(ID)
    text = ""
    html = ""
    attachments = []
    for part in mailMap['parts']:
        if part['meta']['type'] == 'text/plain':
            ## falls charset nicht stimmt, raten, sonst mit gewalt :)
            try:
                text = part['data'].decode(part['meta']['charset'])
            except:
                # print('guessing charset')
                try:
                    text = part['data'].decode('ISO-8859-1')
                except:
                    # print('forcing charset')
                    text = part['data'].decode('UTF-8','ignore')
            text = flask.Markup(text.replace('\n', '<br>'))
        elif part['meta']['type'] == 'text/html':
            try:
                html = part['data'].decode(part['meta']['charset'])
            except:
                # print('guessing charset')
                try:
                    html = part['data'].decode('ISO-8859-1')
                except:
                    # print('forcing charset')
                    html = part['data'].decode('UTF-8','ignore')
            html = flask.Markup(html)
        else:
            if part['meta']['filename'] is not None:
                attachments.append(part)
    return flask.render_template('mail.html',
                                    subject = mailMap['subject'], 
                                    html=html, 
                                    text=text,
                                    ID=ID, 
                                    attachments=attachments)


# attachment serving
@app.route('/<ID>/<filename>')
def downloadAttachment(ID, filename):
    if not 'username' in flask.session:
        return 'You are not logged in <br><a href="' + flask.url_for('login') + '">login</a>'
    attachment = getAttachment(ID,filename) 
    return flask.send_file(BytesIO(attachment))


if __name__ == '__main__':
    app.run(host='localhost', port=SMA_PORT, debug=True)
