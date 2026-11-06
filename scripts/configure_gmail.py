"""Run locally to configure Gmail; the App Password is entered without echo."""
import getpass
from pathlib import Path
import re
from dotenv import set_key


def main():
    address=input('Gmail sender address: ').strip()
    if not re.fullmatch(r'[^\s@]+@gmail\.com',address,re.I):raise SystemExit('Enter your Gmail address.')
    password=getpass.getpass('Google App Password (hidden): ').replace(' ','')
    if len(password)!=16:raise SystemExit('Use the 16-character Google App Password, not your normal password.')
    path=Path(__file__).resolve().parents[1]/'.env'
    for key,value in dict(MAIL_HOST='smtp.gmail.com',MAIL_PORT='587',MAIL_FROM=address,MAIL_USERNAME=address,MAIL_PASSWORD=password,MAIL_SSL='false').items():
        set_key(str(path),key,value)
    print('Gmail configuration saved locally. No email has been sent.')
    print('Restart with: powershell -ExecutionPolicy Bypass -File scripts\\restart_local.ps1')


if __name__=='__main__':main()
