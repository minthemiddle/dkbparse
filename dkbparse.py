#!/usr/bin/env python3
# /// script
# requires-python = ">=3.6"
# dependencies = [
#     "click",
# ]
# ///

import subprocess
import re
import logging
import csv
import os
import sys
import click

from datetime import datetime
from decimal import Decimal

# https://www.bonify.de/abkuerzungen-im-verwendungszweck

# patterns that are re-used in regular expressions
DATE = r"(\d\d)\.(\d\d)\.(\d\d\b|\d\d\d\d\b)"
DATE_NO_YEAR = r"(\d\d)\.(\d\d)\."
DECIMAL = r"\d{1,3}(?:\.\d{3})*(?:,\d+)?"
DECIMAL_FIXED_POINT = r"\d{1,3}(?:\.\d{3})*(?:,\d{2})"
CURRENCY = r"AED|AFN|ALL|AMD|ANG|AOA|ARS|AUD|AWG|AZN|BAM|BBD|BDT|BGN|BHD|BIF|BMD|BND|BOB|BRL|BSD|BTN|BWP|BYR|BZD|CAD|CDF|CHF|CLP|CNY|COP|CRC|CUC|CUP|CVE|CZK|DJF|DKK|DOP|DZD|EGP|ERN|ETB|EUR|FJD|FKP|GBP|GEL|GGP|GHS|GIP|GMD|GNF|GTQ|GYD|HKD|HNL|HRK|HTG|HUF|IDR|ILS|IMP|INR|IQD|IRR|ISK|JEP|JMD|JOD|JPY|KES|KGS|KHR|KMF|KPW|KRW|KWD|KYD|KZT|LAK|LBP|LKR|LRD|LSL|LYD|MAD|MDL|MGA|MKD|MMK|MNT|MOP|MRO|MUR|MVR|MWK|MXN|MYR|MZN|NAD|NGN|NIO|NOK|NPR|NZD|OMR|PAB|PEN|PGK|PHP|PKR|PLN|PYG|QAR|RON|RSD|RUB|RWF|SAR|SBD|SCR|SDG|SEK|SGD|SHP|SLL|SOS|SPL|SRD|STD|SVC|SYP|SZL|THB|TJS|TMT|TND|TOP|TRY|TTD|TVD|TWD|TZS|UAH|UGX|USD|UYU|UZS|VEF|VND|VUV|WST|XAF|XCD|XDR|XOF|XPF|YER|ZAR|ZMW|ZWD"  # ISO 4217
TEXT = r"\S.*\S"
SIGN = r"[\+\-SH]"
CARD_NO = r"\b[0-9X]{4}\s[0-9X]{4}\s[0-9X]{4}\s[0-9X]{4}\b"
BLANK = r"\s{3,}"
MONTHS = dict(Januar=1, Februar=2, März=3, April=4, Mai=5, Juni=6, Juli=7, August=8, September=9, Oktober=10, November=11, Dezember=12)

re_visa_filename = re.compile(
    r"Kreditkartenabrechnung_\d\d\d\d[_x]{8}\d\d\d\d_per_\d\d\d\d_\d\d_\d\d.pdf"
)
# Old format: Kontoauszug_1010001491_Nr_2015_004_per_2015_04_02.pdf
re_filename_old = re.compile(
    r"Kontoauszug_\d{8,10}_Nr_\d\d\d\d_\d\d\d_per_\d\d\d\d_\d\d_\d\d.pdf"
)
# New format: Kontoauszug_8_2024_vom_05.08.2024_zu_Konto_1010001491.pdf
re_filename_new = re.compile(
    r"Kontoauszug_\d{1,2}_\d\d\d\d_vom_\d\d\.\d\d[._]\d\d\d\d_?_?zu_Konto_\d{8,10}\.pdf"
)
# Combined pattern to match either old or new format
re_filename = re.compile(
    r"Kontoauszug_(?:\d{8,10}_Nr_\d\d\d\d_\d\d\d_per_\d\d\d\d_\d\d_\d\d|\d{1,2}_\d\d\d\d_vom_\d\d\.\d\d[._]\d\d\d\d_?_?zu_Konto_\d{8,10})\.pdf"
)

# Old format patterns
re_range = re.compile(
    rf"Kontoauszug Nummer (?P<no>\d*) / (?P<year>\d*) vom (?P<from>{DATE}) bis (?P<to>{DATE})"
)
re_account = re.compile(r"Kontonummer (?P<account>[0-9]*) / IBAN (?P<iban>[A-Z0-9 ]*)")
re_balance_old = re.compile(
    rf"ALTER KONTOSTAND\s*(?P<old>{DECIMAL}) (?P<sign>{SIGN}) EUR"
)
re_balance_new = re.compile(
    rf"NEUER KONTOSTAND\s*(?P<new>{DECIMAL}) (?P<sign>{SIGN}) EUR"
)
re_table_header = re.compile(
    r"(?P<booked>Bu.Tag)\s+(?P<valued>Wert)\s+(?P<comment>Wir haben für Sie gebucht)\s+(?P<minus>Belastung in EUR)\s+(?P<plus>Gutschrift in EUR)"
)
re_transaction = re.compile(
    rf"^\s*(?P<booked>{DATE_NO_YEAR}){BLANK}"
    rf"(?P<valued>{DATE_NO_YEAR}){BLANK}"
    rf"(?P<type>{TEXT}){BLANK}"
    rf"(?P<value>{DECIMAL_FIXED_POINT})$"
)
re_transaction_details = re.compile(
    rf"((?:{BLANK})|(?:{DATE_NO_YEAR}\s+{DATE_NO_YEAR}\s+))" rf"(?P<line>{TEXT})"
)

# New format patterns
re_statement_new = re.compile(
    r"Kontoauszug (?P<no>\d{1,2})/(?P<year>\d{4})"
)
re_balance_old_new = re.compile(
    rf"Kontostand am (?P<date>{DATE}), Auszug Nr\. \d+\s+(?P<old>{DECIMAL})"
)
re_balance_new_new = re.compile(
    rf"Kontostand am (?P<date>{DATE}) um \d{2}:\d{2} Uhr\s+(?P<new>{DECIMAL})"
)
re_table_header_new = re.compile(
    r"Datum\s+Erläuterung\s+Betrag Soll EUR\s+Betrag Haben EUR"
)
re_transaction_new_soll = re.compile(
    r"^\s*(?P<booked>\d{2}\.\d{2}\.\d{4})\s+(?P<type>.+?)\s+(?P<soll>-?\d{1,3}(?:\.\d{3})*(?:,\d{2}))\s*$"
)
re_transaction_new_haben = re.compile(
    r"^\s*(?P<booked>\d{2}\.\d{2}\.\d{4})\s+(?P<type>.+?)\s{70,}(?P<haben>\d{1,3}(?:\.\d{3})*(?:,\d{2}))\s*$"
)

# re_visa_table_header = re.compile(r"(?P<booked>Datum)\s+(?P<valued>Datum Angabe des Unternehmens /)\s+(?P<curency>Währung)\s+(?P<foreign_value>Betrag)\s+(?P<rate>Kurs)\s+(?P<value>Betrag in)")
re_visa_balance_new = re.compile(
    rf"\s*Neuer Saldo\s*(?P<value>{DECIMAL})\s*(?P<sign>{SIGN})?"
)
re_visa_balance_old = re.compile(
    rf"\s*(?P<valued>{DATE})\s+Saldo letzte Abrechnung\s+(?P<value>{DECIMAL})\s*(?P<sign>{SIGN})"
)
re_visa_subtotal = re.compile(
    rf"\s*(Zwischensumme|Übertrag von) Seite \d+\s+(?P<value>{DECIMAL})\s*(?P<sign>{SIGN})"
)
re_visa_month_year = re.compile(r"\s+Abrechnung:\s+(?P<month>\b\S*\b) (?P<year>\d\d\d\d)")

re_visa_range = re.compile(rf"Ihre Abrechnung vom (?P<from>{DATE}) bis (?P<to>{DATE})")

re_visa_comment_extended = re.compile(r"^\s{18}(?P<comment_extended>\S.*)$")

re_visa_transaction_foreign = re.compile(
    rf"^(?P<booked>{DATE})\s+"
    rf"(?P<valued>{DATE})\s+"
    rf"(?P<comment>{TEXT})\s+"
    rf"(?P<currency>{CURRENCY})\s+"
    rf"(?P<foreign>{DECIMAL})\s+"
    rf"(?P<rate>{DECIMAL})\s+"
    rf"(?P<value>{DECIMAL})\s*"
    rf"(?P<sign>{SIGN})$"
)

re_visa_transaction = re.compile(
    rf"^(?P<booked>{DATE})?\s+"
    rf"(?P<valued>{DATE})?\s+"
    rf"(?P<comment>{TEXT})\s+"
    rf"(?P<value>{DECIMAL})\s*"
    rf"(?P<sign>{SIGN})$"
)

re_visa_account = re.compile(
    rf".*((?:DKB-VISA-Card\:)|(?:VISA\sCard-Nummer\:))\s*(?P<account>{CARD_NO})"
)
# VISA Card-Nummer:
# re_visa_owner = re.compile(r"\s*(?:Karteninhaber:)\s*(?P<owner>.*)")


def transactions_to_csv(f, transactions):
    """writes transactions as CSV to f"""
    keys = ['account','year','statement','transaction','booked','valued','value','type','payee','comment']
    transactions = sorted(transactions, key=lambda t: t["valued"], reverse=True)
    dict_writer = csv.DictWriter(f, keys)
    dict_writer.writeheader()
    dict_writer.writerows(transactions)

def transactions_to_moneymoney_csv(f, transactions):
    """writes transactions as MoneyMoney CSV to f"""
    # MoneyMoney CSV format:
    # Datum;Wertstellung;Kategorie;Name;Verwendungszweck;Konto;Bank;Betrag;Währung
    fieldnames = ['Datum', 'Wertstellung', 'Kategorie', 'Name', 'Verwendungszweck', 'Konto', 'Bank', 'Betrag', 'Währung']

    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()

    # Sort by value date (newest first)
    transactions = sorted(transactions, key=lambda t: t["valued"], reverse=True)

    for transaction in transactions:
        # Extract account info from transaction for the OTHER party
        other_account = ""
        other_bank = ""

        # Try to extract account/bank info from comment if available
        comment = transaction.get('comment', '')
        if 'Referenz:' in comment:
            # This might contain bank info in some cases
            pass

        # For VISA transactions, the original account is the source
        if transaction['type'] == 'VISA':
            other_account = transaction['account'].replace('X', '*')  # Mask some digits for privacy
            other_bank = "VISA"

        # Format dates
        booked_date = transaction['booked'].strftime('%d.%m.%Y')
        valued_date = transaction['valued'].strftime('%d.%m.%Y')

        # Amount - negative for expenses, positive for income
        amount = transaction['value']

        # MoneyMoney expects negative amounts for expenses (Ausgaben)
        # and positive for income (Einnahmen)
        # DKB already follows this convention

        writer.writerow({
            'Datum': booked_date,
            'Wertstellung': valued_date,
            'Kategorie': '',  # Not available in DKB statements
            'Name': transaction['payee'] or transaction['type'],
            'Verwendungszweck': comment,
            'Konto': other_account,
            'Bank': other_bank,
            'Betrag': f"{amount:.2f}".replace('.', ','),  # German decimal format
            'Währung': 'EUR'
        })

def csv_to_transactions(f):
    """Reads transactions as CSV from f"""
    Date = lambda s: datetime.strptime(s, '%Y-%m-%d').date()
    decimal_accuracy = Decimal('0.01')
    converters={'valued': Date, 'booked': Date, 'value': lambda s: Decimal(s).quantize(decimal_accuracy)}
    reader = csv.DictReader(f)
    transactions = []
    for row in reader:
        for key, func in converters.items():
            row[key] = func(row[key])
        transactions.append(row)
    return transactions

def scan_dirs(dirpaths):
    """Recursively scans dirpath for DKB bank or visa statements and returns all parsed transactions and statements"""
    transactions = []
    statements = []
    for dirpath in dirpaths:
        for dirpath, unused_dirnames, filenames in os.walk(dirpath):
            logging.info(f"scanning {dirpath} ...")
            for filename in filenames:
                if re_visa_filename.match(filename):
                    transactions_statement, statement = read_visa_statement(
                        f"{dirpath}/{filename}"
                    )
                    statements.append(statement)
                    transactions.extend(transactions_statement)
                elif re_filename.match(filename):
                    transactions_statement, statement = read_bank_statement(
                        f"{dirpath}/{filename}"
                    )
                    statements.append(statement)
                    transactions.extend(transactions_statement)

    return transactions, statements

def read_pdf_table(fname):
    """Reads contents of a PDF table into a string using pdftotext"""
    completed_process = subprocess.run(
        ["pdftotext", "-layout", fname, "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    err_lines = completed_process.stderr.decode().split("\n")
    for err_line in err_lines:
        logging.debug(f"pdftotext.stderr: {err_line}")
    return completed_process.stdout.decode()


def check_match(re, line, result):
    """calls re.match(line) but also writes the return value to result['match'] and writes match to log"""
    match = re.match(line)
    if match:
        result["match"] = match
        logging.debug(f"'{line}'\t{match.groupdict()}\t{re.pattern}")
    return match


def decimal(s):
    return Decimal(s.replace(".", "").replace(",", "."))


def date(s, format="%d.%m.%Y"):
    return datetime.strptime(s, format).date()


def sign(s):
    return -1 if s in ["-", "S"] else 1


def parse_new_filename(filename):
    """Parse statement info from new DKB filename format"""
    # Extract from: Kontoauszug_8_2024_vom_05.08.2024_zu_Konto_1010001491.pdf
    # or: Kontoauszug_8_2023_vom_07.08_2023_zu_Konto_1010001491.pdf
    basename = os.path.basename(filename)
    if re_filename_new.match(basename):
        parts = basename.replace('.pdf', '').split('_')
        # parts: ['Kontoauszug', '8', '2024', 'vom', '05.08.2024', 'zu', 'Konto', '1010001491']
        # or: ['Kontoauszug', '8', '2023', 'vom', '07.08', '2023', 'zu', 'Konto', '1010001491']
        if len(parts) >= 8 and parts[3] == 'vom':
            statement_no = int(parts[1])
            year = int(parts[2])
            account = parts[-1]  # Last part should be the account number
            return {
                'no': statement_no,
                'year': year,
                'account': account
            }
    return None


def read_bank_statement(pdf):
    """returns transactions list and statement summary extracted from a DKB bank statement"""

    statement = {"file": pdf}
    transactions = []
    res = {}

    # Try to extract basic info from filename for new format
    filename_info = parse_new_filename(pdf)
    if filename_info:
        statement.update(filename_info)

    table = read_pdf_table(pdf)
    lines = table.splitlines()

    # Detect format by checking for new format indicators
    is_new_format = any(re_statement_new.search(line) for line in lines)

    match_table_header = None
    transaction_number = 1

    for line in lines:
        if is_new_format:
            # New format patterns
            if check_match(re_statement_new, line, res):
                match = res["match"]
                statement["no"] = int(match.group("no"))
                statement["year"] = int(match.group("year"))
            elif check_match(re_balance_old_new, line, res):
                match = res["match"]
                statement["balance_old"] = decimal(match.group("old"))
            elif check_match(re_balance_new_new, line, res):
                match = res["match"]
                statement["balance_new"] = decimal(match.group("new"))
            elif check_match(re_table_header_new, line, res):
                match_table_header = res["match"]
            elif check_match(re_transaction_new_soll, line, res):
                match = res["match"]
                # Transaction in Soll (debit) column - use as-is (already has sign)
                if match.group("soll"):
                    value = decimal(match.group("soll"))
                else:
                    value = 0

                transactions.append(
                    {
                        "account": f'{statement["account"]:0>16}',
                        "year": statement['year'],
                        "statement": f"{statement['no']:02}",
                        "transaction": f"{transaction_number:03}",
                        "booked": date(match.group("booked")),
                        "valued": date(match.group("booked")),  # New format uses same date
                        "type": match.group("type").strip(),
                        "value": value,
                        "payee": "",
                        "comment": "",
                    }
                )
                transaction_number += 1
            elif check_match(re_transaction_new_haben, line, res):
                match = res["match"]
                # Transaction in Haben (credit) column - use as-is (already positive)
                if match.group("haben"):
                    value = decimal(match.group("haben"))
                else:
                    value = 0

                transactions.append(
                    {
                        "account": f'{statement["account"]:0>16}',
                        "year": statement['year'],
                        "statement": f"{statement['no']:02}",
                        "transaction": f"{transaction_number:03}",
                        "booked": date(match.group("booked")),
                        "valued": date(match.group("booked")),  # New format uses same date
                        "type": match.group("type").strip(),
                        "value": value,
                        "payee": "",
                        "comment": "",
                    }
                )
                transaction_number += 1
            elif transactions and line.startswith('              ') and line.strip() and not re_statement_new.match(line):
                # Transaction details for new format - lines starting with exactly 14 spaces
                if not transactions[-1]["payee"]:
                    transactions[-1]["payee"] = line.strip()
                    transactions[-1]["comment"] = line.strip()
                else:
                    transactions[-1]["comment"] += " " + line.strip()
        else:
            # Old format patterns
            if check_match(re_range, line, res):
                match = res["match"]
                statement["no"] = int(match.group("no"))
                statement["year"] = int(match.group("year"))
                statement["from"] = date(match.group("from"))
                statement["to"] = date(match.group("to"))
            elif check_match(re_account, line, res):
                match = res["match"]
                statement["account"] = match.group("account")
                statement["iban"] = match.group("iban")
            elif check_match(re_balance_old, line, res):
                match = res["match"]
                statement["balance_old"] = decimal(match.group("old")) * sign(
                    match.group("sign")
                )
            elif check_match(re_balance_new, line, res):
                match = res["match"]
                statement["balance_new"] = decimal(match.group("new")) * sign(
                    match.group("sign")
                )
            elif check_match(re_table_header, line, res):
                match_table_header = res["match"]
            elif check_match(re_transaction, line, res):
                match = res["match"]
                value = decimal(match.group("value"))
                if match.start("value") < match_table_header.end("minus"):
                    value = -value
                transactions.append(
                    {
                        "account": f'{statement["account"]:0>16}',
                        "year": statement['year'],
                        "statement": f"{statement['no']:02}",
                        "transaction": f"{transaction_number:03}",
                        "booked": date(match.group("booked") + str(statement["year"])),
                        "valued": date(match.group("valued") + str(statement["year"])),
                        "type": match.group("type").strip(),
                        "value": value,
                        "payee": "",
                        "comment": "",
                    }
                )
                transaction_number += 1
            elif check_match(re_transaction_details, line, res) and match_table_header:
                match = res["match"]
                if match.start("line") == match_table_header.start("comment"):
                    if not transactions[-1]["payee"]:
                        transactions[-1]["payee"] = match.group("line")
                        transactions[-1]["comment"] = transactions[-1]["payee"]

                    else:
                        transactions[-1]["comment"] += " " + match.group("line") # note: line might be missing spaces anywhere
            else:
                logging.debug(f"'{line}'\tNOT MATCHED")

    # check for parsing errors
    if "balance_new" in statement and "balance_old" in statement:
        transactions_sum = sum(map(lambda t: t["value"], transactions))
        balance_difference = statement["balance_new"] - statement["balance_old"]
        if transactions_sum != balance_difference:
            logging.error(
                f"parsed balance difference of {balance_difference} and transaction sum of {transactions_sum} for {pdf}!"
            )
    else:
        logging.warning(f"Missing balance information for {pdf}. Found keys: {list(statement.keys())}")

    return transactions, statement


def read_visa_statement_lines(lines):
    """returns transactions list and statement summary extracted from a DKB VISA card statement text lines"""
    statement = {}
    transactions = []
    statement["balance_old"] = 0
    transaction_number = 1
    res = {}

    for line in lines:
        if check_match(re_visa_balance_old, line, res):
            match = res["match"]
            value = decimal(match.group("value")) * sign(match.group("sign"))
            statement["balance_old"] = value
        elif check_match(re_visa_month_year, line, res):
            match = res["match"]
            statement["month"] = match.group("month")
            statement["no"] = MONTHS[statement["month"]]
            statement["year"] = match.group("year")
        elif check_match(re_visa_range, line, res):
            match = res["match"]
            statement["from"] = date(match.group("from"))
            statement["to"] = date(match.group("to"))
        elif check_match(re_visa_balance_new, line, res):
            match = res["match"]
            value = decimal(match.group("value")) * sign(match.group("sign"))
            statement["balance_new"] = value
        elif check_match(re_visa_subtotal, line, res):
            pass
        elif check_match(re_visa_transaction_foreign, line, res) or check_match(
            re_visa_transaction, line, res
        ):
            match = res["match"]
            value = decimal(match.group("value")) * sign(match.group("sign"))
            if match.group("booked"):
                booked = match.group("booked")
                booked = date(booked[:6] + "20" + booked[6:])
            if match.group("valued"):
                valued = match.group("valued")
                valued = date(valued[:6] + "20" + valued[6:])
            transactions.append(
                {
                    "account": ''.join(statement['account'].split()),
                    "year": statement["year"],
                    "statement": f"{statement['no']:02}",
                    "transaction": f"{transaction_number:03}",
                    "booked": booked,
                    "valued": valued,
                    "type": "VISA",
                    "value": value,
                    "payee": "",
                    "comment": match.group("comment"),
                }
            )
            transaction_number += 1
        elif check_match(re_visa_comment_extended, line, res):
            match = res["match"]
            transactions[-1]["comment"] += " " + match["comment_extended"]
        else:
            logging.debug(f"'{line}'\tNOT MATCHED")
        if check_match(re_visa_account, line, res):
            match = res["match"]
            statement["account"] = match["account"]

    return transactions, statement


def read_visa_statement(pdf):
    """returns transactions list and statement summary extracted from a DKB VISA card statement PDF file"""
    logging.info(f"reading VISA statement {pdf} ...")
    table = read_pdf_table(pdf)
    lines = table.splitlines()

    transactions, statement = read_visa_statement_lines(lines)
    statement['file'] = pdf

    # check for parsing errors
    transactions_sum = sum(map(lambda t: t["value"], transactions))
    balance_difference = statement["balance_new"] - statement["balance_old"]
    if transactions_sum != balance_difference:
        logging.error(
            f"parsed balance difference of {balance_difference} and transaction sum of {transactions_sum} for {pdf}!"
        )

    return transactions, statement

@click.command()
@click.argument('directories', nargs=-1, required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output', '-o', type=click.File('w'), default=sys.stdout, help='Output CSV file (default: stdout)')
@click.option('--format', '-f', type=click.Choice(['dkb', 'moneymoney']), default='dkb', help='Output format: dkb (default) or moneymoney')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(directories, output, format, verbose):
    """
    Parse DKB bank and VISA statement PDFs.

    DIRECTORIES: One or more directories containing DKB PDF statements.
    The script will scan each directory recursively for both bank account statements
    and VISA card statements.

    Examples:
        # Parse a single directory with bank statements
        uv run dkbparse.py ~/documents/dkb/statements/

        # Parse multiple directories (bank + visa)
        uv run dkbparse.py ~/dkb/account/ ~/dkb/visa/

        # Save to file instead of stdout
        uv run dkbparse.py ~/dkb/ --output transactions.csv

        # Export in MoneyMoney format
        uv run dkbparse.py ~/dkb/ --format moneymoney --output moneymoney.csv

        # Enable verbose logging
        uv run dkbparse.py ~/dkb/ --verbose
    """
    if verbose:
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    else:
        logging.basicConfig(level=logging.WARNING)

    transactions, statements = scan_dirs(list(directories))

    click.echo(f"Parsed {len(transactions)} transactions from {len(statements)} statements", err=True)

    if format == 'moneymoney':
        transactions_to_moneymoney_csv(output, transactions)
    else:
        transactions_to_csv(output, transactions)

if __name__ == '__main__':
    main()