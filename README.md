# dkbparse
PDF parser for DKB bank and VISA statements

Can be handy for further processing your bank data (e.g. with [beancount](https://github.com/beancount/beancount)).

## Features
- Can be used as shell script
- CSV export

## Requirements
You will need to have Python 3, uv, and pdftotext installed.

## Usage

### With uv (Recommended)
You can run `dkbparse.py` as a script using uv. The script automatically detects both bank and VISA statements:

```bash
# Parse a single directory containing DKB statements
$ uv run dkbparse.py ~/documents/dkb/statements/

# Parse multiple directories
$ uv run dkbparse.py ~/dkb/account/ ~/dkb/visa/

# Save output to a file
$ uv run dkbparse.py ~/dkb/ --output transactions.csv

# Export in MoneyMoney format (for import into MoneyMoney app)
$ uv run dkbparse.py ~/dkb/ --format moneymoney --output moneymoney.csv

# Enable verbose logging to see what's being processed
$ uv run dkbparse.py ~/dkb/ --verbose

# Get help on available options
$ uv run dkbparse.py --help
```

**Output**:
```csv
account,year,statement,transaction,booked,valued,value,type,payee,comment
0000001234567890,2019,01,001,2019-01-02,2018-12-31,-250.00,Überweisung,Tante Helga,ÜBERWEISUNG DATUM 29.12.2018, 05.33 UHR 1.TAN 123456
...
```

## Output Formats

### DKB Format (default)
Original CSV format with DKB-specific fields:
```csv
account,year,statement,transaction,booked,valued,value,type,payee,comment
0000001234567890,2019,01,001,2019-01-02,2018-12-31,-250.00,Überweisung,Tante Helga,ÜBERWEISUNG DATUM 29.12.2018, 05.33 UHR 1.TAN 123456
...
```

### MoneyMoney Format
MoneyMoney-compatible CSV format for easy import:
```csv
Datum;Wertstellung;Kategorie;Name;Verwendungszweck;Konto;Bank;Betrag;Währung
02.01.2019;31.12.2018;;Tante Helga;ÜBERWEISUNG DATUM 29.12.2018, 05.33 UHR 1.TAN 123456;;;-250,00;EUR
...
```

**MoneyMoney field mapping**:
- **Datum**: Booking date (when transaction was booked)
- **Wertstellung**: Value date (when transaction value was effective)
- **Kategorie**: Empty (not available in DKB statements)
- **Name**: Payee or transaction type
- **Verwendungszweck**: Full transaction description/comment
- **Konto**: Other party's account (VISA card number for card transactions)
- **Bank**: Other party's bank (VISA for card transactions)
- **Betrag**: Amount in German format (negative = expenses, positive = income)
- **Währung**: Currency (EUR)

## Transaction Format

The script outputs CSV data with the following structure. A transaction dict looks like this:
```
{
    'account': '0000001234567890',
    'year': '2019',
    'statement': '01',
    'transaction': '001',
    'booked': datetime.date(2019, 1, 2), 
    'valued': datetime.date(2018, 12, 31), 
    'type': 'Überweisung', 
    'value': Decimal('-250.00'), 
    'payee': 'Tante Helga',
    'comment': 'ÜBERWEISUNG DATUM 29.12.2018, 05.33 UHR 1.TAN 123456'
}
```

A statement dict looks like this
```
{   
    'account': '9451359782',
    'year': '2019'
    'no': '1',
    'from': datetime.datetime(2018, 12, 29, 0, 0),
    'to': datetime.datetime(2019, 1, 3, 0, 0),
    'balance_old': Decimal('1443.81'),
    'balance_new': Decimal('487.33'),
    'file': 'Kontoauszug_9451359782_Nr_2019_001_per_2019_03_01.pdf'
}
```

The script will output an error if the sum of all transactions of a statement does not correspond to the stated balance difference. This will help you to identify cases where the parser fails to parse a statement.

## Performance

The script scans around 100 PDF files (or 2500 transactions) per second.

## Limitations

The main limitation of this approach is that the output depends on the version of the installed `pdftotext` ([Poppler](https://poppler.freedesktop.org/)). Different results on different platforms can not be excluded. For example, using pdftotext version 0.86.1, I occasionally get the following error, which appears to be a known issue.
```
Syntax Warning: FoFiType1::parse a line has more than 255 characters, we don't support this
```
