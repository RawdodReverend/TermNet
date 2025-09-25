import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from typing import List, Optional

class GmailTool:
    """Handles Gmail communication: send, read, search, delete"""

    def __init__(self, email_address: str, password: str,
                 imap_server='imap.gmail.com', smtp_server='smtp.gmail.com'):
        self.email_address = email_address
        self.password = password
        self.imap_server = imap_server
        self.smtp_server = smtp_server

    # ---- Email Sending ----
    def send_email(self, to: str, subject: str, body: str):
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self.email_address
        msg['To'] = to
        with smtplib.SMTP_SSL(self.smtp_server, 465) as smtp:
            smtp.login(self.email_address, self.password)
            smtp.send_message(msg)

    # ---- SMS Sending via email gateway ----
    def send_sms(self, phone_number: str, carrier_gateway: str, message: str):
        sms_address = f"{phone_number}@{carrier_gateway}"
        self.send_email(sms_address, "", message)

    # ---- Email Reading ----
    def list_unread(self, folder='inbox') -> List[str]:
        mail = imaplib.IMAP4_SSL(self.imap_server)
        mail.login(self.email_address, self.password)
        mail.select(folder)
        status, response = mail.search(None, '(UNSEEN)')
        messages = []
        if status == 'OK':
            for num in response[0].split():
                status, data = mail.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])
                messages.append(f"{msg['From']}: {msg['Subject']}")
        mail.logout()
        return messages

    def search_emails(self, query: str, folder='inbox') -> List[str]:
        mail = imaplib.IMAP4_SSL(self.imap_server)
        mail.login(self.email_address, self.password)
        mail.select(folder)
        status, response = mail.search(None, f'(BODY "{query}")')
        results = []
        if status == 'OK':
            for num in response[0].split():
                status, data = mail.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])
                results.append(f"{msg['From']}: {msg['Subject']}")
        mail.logout()
        return results

    def delete_email(self, uid: str, folder='inbox'):
        mail = imaplib.IMAP4_SSL(self.imap_server)
        mail.login(self.email_address, self.password)
        mail.select(folder)
        mail.store(uid, '+FLAGS', '\\Deleted')
        mail.expunge()
        mail.logout()
