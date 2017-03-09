#!/usr/bin/env python3

import os
import poplib
import notmuch
import flask
import datetime
import io
import hashlib
import threading


smaPath = os.path.dirname(os.path.realpath(__file__))

db = None

app = flask.Flask(__name__)


##  reread database all the time
def rereadDatabase():
    global db
    db = notmuch.Database()
    print('db reread')
    threading.Timer(60*60, rereadDatabase).start()


rereadDatabase()

## muss für unicorn nen fester wert sein, damit nicht jeder worker nen anderen key hat.
# app.secret_key = os.urandom(24)
app.secret_key = b'\x10\xe2A\xaa\xbb\x9f\xab\x19\x023\x01\x91\xc7G\xb3\xb8\xccw\x94\x7f\xe3\xee\x81\x0f'

# test:1234
# user:user
users = {
        'test': '7110eda4d09e062aa5e4a390b0a572ac0d2c0220',
        'user': '12dea96fec20593566ab75692c9949596833adc9'
        }


### notmuch handling

def smaSearch(q):
    msgs = notmuch.Query(db, q).search_messages()
    msglist = list(msgs)[:20]
    return msglist


def mailList(smaQuery):
    search = smaSearch(smaQuery)
    mails = [
                {
                    'filename': x.get_filename(), 
                    'date': datetime.datetime.fromtimestamp(int(x.get_date())).strftime('%Y-%m-%d %H:%M:%S'),
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
    return flask.send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


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
        mails = mailList(smaQuery)
        return flask.render_template("list.html", mails=mails)


# delete an email
@app.route('/delete', methods=['GET', 'POST'])
def delete():
    if flask.request.method == 'POST':
        # We need rw access,
        # maybe its blocked
        while True:
            try:
                db_rw = notmuch.Database(mode=1)
                break
            except:
                # try harder :)
                pass
        # db is now in rw mode!
        for mailId in flask.request.form:
            for filename in smaSearch('id:' + mailId)[0].get_filenames():
                print(filename)
                db_rw.remove_message(filename)
                os.remove(filename)
        # we do not need rw access anymore
        db_rw.close()
        del db_rw
        # reload database!
        global db
        db = notmuch.Database()
    return flask.redirect(flask.url_for('sma'))


# login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == 'POST':
        userName = flask.request.form['username']
        passwordHash = hashlib.sha1( flask.request.form['password'].encode('utf-8') ).hexdigest()
        # print(userName, passwordHash)
        if userName in users:
            if passwordHash == users[userName]: 
                flask.session.permanent = True
                flask.session['username'] = userName
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
    return flask.send_file(io.BytesIO(attachment))


if __name__ == '__main__':
    app.run(host='localhost', port=64004)
