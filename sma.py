#!/usr/bin/env python3

import os
import poplib
import notmuch
import flask
import datetime
import io
import hashlib


smaPath = os.path.dirname(os.path.realpath(__file__))

db = notmuch.Database()

app = flask.Flask(__name__)

app.secret_key = os.urandom(24)

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
    if flask.request.method == 'GET':
        return '''  <form action="" method="post">
                        <p><input type=text name=query>
                        <p><input type=submit value=search!>
                    </form>
                '''
    elif flask.request.method == 'POST':
        smaQuery = flask.request.form['query']
        mails = mailList(smaQuery)
        return flask.render_template("list.html", mails=mails)


# login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == 'POST':
        userName = flask.request.form['username']
        passwordHash = hashlib.sha1( flask.request.form['password'].encode('utf-8') ).hexdigest()
        print(userName, passwordHash)
        if userName in users:
            if passwordHash == users[userName]: 
                flask.session.permanent = True
                flask.session['username'] = userName
                return flask.redirect(flask.url_for('sma'))
    return '''
        <form action="" method="post">
            <p><input type=text name=username>
            <p><input type=text name=password>
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
                print('guessing charset')
                try:
                    text = part['data'].decode('ISO-8859-1')
                except:
                    print('forcing charset')
                    text = part['data'].decode('UTF-8','ignore')
            text = flask.Markup(text.replace('\n', '<br>'))
        elif part['meta']['type'] == 'text/html':
            try:
                html = part['data'].decode(part['meta']['charset'])
            except:
                print('guessing charset')
                try:
                    html = part['data'].decode('ISO-8859-1')
                except:
                    print('forcing charset')
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
    attachment = getAttachment(ID,filename) 
    return flask.send_file(io.BytesIO(attachment))


if __name__ == '__main__':
    app.run(host='localhost', port=64004)
