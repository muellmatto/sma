#!/usr/bin/env python3

import os
import poplib
import notmuch
import flask
import datetime
import io


smaPath = os.path.dirname(os.path.realpath(__file__))

db = notmuch.Database()

app = flask.Flask(__name__)

app.secret_key = os.urandom(24)




## das hier muss dringend verbesser werden:
attachments = []

def smaSearch(q):
    msgs = notmuch.Query(db, q).search_messages()
    msglist = list(msgs)[:20]
    return msglist


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
                    for i in range(len(mailMeta)) 
                ]
    mailMap = {
                'subject': mail.get_header('subject'),
                'parts' : parts 
            }
    return mailMap


@app.route('/favicon.ico')
def favicon():
    return flask.send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/', methods=['GET', 'POST'])
def sma():
    if flask.request.method == 'GET':
        return '''  <form action="" method="post">
                        <p><input type=text name=query>
                        <p><input type=submit value=search!>
                    </form>
                '''
    elif flask.request.method == 'POST':
        # smaQuery = 'from:sarahrotthues'
        # smaQuery = 'from:leifheit'
        # smaQuery = ''
        smaQuery = flask.request.form['query']
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
        return flask.render_template("list.html", mails=mails)


@app.route('/<ID>')
def showMail(ID):
    global attachments
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
            attachments.append(part)
        #>>> f= open('test.pdf','bw')
        #>>> f.write(m.get_part(5))
        #2741550
        #>>> f.close()
    # store attachments so we do not have to rebuild mailMap for every download
    # flask.session['attachments'] = attachments
    return flask.render_template('mail.html',
                                    subject = mailMap['subject'], 
                                    html=html, 
                                    text=text, 
                                    attachments=attachments)


@app.route('/get/<filename>')
def getAttachment(filename):
    global attachments
    # attachments = flask.session['attachments']
    for attachment in attachments:
        if attachment['meta']['filename'] == str(filename):
            return flask.send_file(io.BytesIO(attachment['data']))


if __name__ == '__main__':
    app.run(host='localhost', port=64004)
