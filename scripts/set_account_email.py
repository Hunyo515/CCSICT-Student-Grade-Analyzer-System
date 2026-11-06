"""Local operator helper for verified account email setup/recovery."""
import argparse
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import Config
import oracledb


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('username');args=parser.parse_args()
    address=input('Verified email address for this account: ').strip()
    if len(address.encode())>150 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',address):raise SystemExit('Invalid email address.')
    with oracledb.connect(user=Config.ORACLE_USER,password=Config.ORACLE_PASSWORD,dsn=Config.ORACLE_DSN) as conn:
        if Config.ORACLE_SCHEMA:conn.current_schema=Config.ORACLE_SCHEMA
        with conn.cursor() as cursor:
            cursor.execute('SELECT user_id,role FROM users WHERE username=:name',name=args.username)
            row=cursor.fetchone()
            if not row:raise SystemExit('Account not found. No change made.')
            cursor.execute('UPDATE users SET email=:address,updated_at=SYSTIMESTAMP WHERE user_id=:user_key',address=address,user_key=row[0])
            cursor.execute("INSERT INTO activity_log(message) VALUES(:message)",message=f'Local operator updated verified email for user {row[0]}.')
        conn.commit()
    print('Registered email updated. Existing sessions are invalidated on their next request.')


if __name__=='__main__':main()
