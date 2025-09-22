# Debian install sqlserver odbc
# apt install -y python3-pip python3-dev unixodbc-dev unixodbc gcc g++
# install pyodbc
# installation verification: python3 -c "import pyodbc; print('pyodbc installed:', pyodbc.version)"
# check odbc driver verison: odbcinst -q -d
# output: [ODBC Driver 17 for SQL Server]    => should be {ODBC Driver 17 for SQL Server}

import pyodbc
import os
from typing import Optional

server = os.getenv('DB_SERVER')
database = os.getenv('DB_DATABASE')
username = os.getenv('DB_USERNAME')
password = os.getenv('DB_PASSWORD')
driver = "{ODBC Driver 17 for SQL Server}"
connection_timeout = 120
login_timeout = 120


def get_sqlserver_connection():
    try:
        conn = pyodbc.connect(
            f'DRIVER={driver};'
            f'SERVER={server};'
            f'DATABASE={database};'
            f'UID={username};'
            f'PWD={password};'
            'Encrypt=yes;'
            'TrustServerCertificate=no;'
            f'Connection Timeout={connection_timeout};'
            f'Login Timeout={login_timeout};'
        )
        
        return conn
    except pyodbc.Error as e:
        raise e


def get_user_by_id(user_id: int, conn=None) -> Optional[dict]:
    """根据ID获取用户"""
    select_sql = "SELECT * FROM tb_user WHERE id = ?"
    conn = None
    try:
        if conn is None:
            conn = get_sqlserver_connection()
        with conn.cursor() as cursor:
            cursor.execute(select_sql, (user_id,))
            row = cursor.fetchone()
            
            if row:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            else:
                return None
    except pyodbc.Error as e:
        print(f"Error fetching user: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    print(get_user_by_id(1))
