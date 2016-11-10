#!/usr/bin/env python3

import os
import poplib
import notmuch
import flask
import datetime
import base64

smaPath = os.path.dirname(os.path.realpath(__file__))
db = notmuch.Database()
app = flask.Flask(__name__)


def smaSearch(q):
    msgs = notmuch.Query(db, q).search_messages()
    msglist = list(msgs)
    return msglist


@app.route('/favicon.ico')
def favicon():
    return flask.send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/')
def sma():
    # smaQuery = 'from:sarahrotthues'
    # smaQuery = 'from:leifheit'
    smaQuery = ''
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
    return flask.render_template("index.html", mails=mails)


@app.route('/<ID>')
def showMail(ID):
    search = smaSearch('id:' + str(ID))
    if len(search) == 0:
        return 'something went wrong!'
    mail = search[0]
    print(mail.get_filename())
    text = ""
    html = ""
    attachments = []
    for part in mail.get_message_parts():
        if part.get_content_type() == 'text/plain':
            text = part.get_payload()
        elif part.get_content_type() == 'text/html':
            html = part.get_payload()
        else: 
            attachments.append({'type': part.get_content_type(), 'name': part.get_filename(), 'data': part.get_payload()})
    if mail.get_header('content-transfer-encoding') == 'base64':
        print('dios mio')
        # text = base64.standard_b64decode(text).decode('UTF-8', 'ignore')
        # html = base64.standard_b64decode(html).decode('UTF-8', 'ignore')
    return flask.render_template('mail.html',
                                    subject = mail.get_header('subject'), 
                                    html=flask.Markup(html), 
                                    text=flask.Markup(text.replace('\n','<br>')), 
                                    attachments=attachments)


if __name__ == '__main__':
    app.run(host='localhost', port=64004)
