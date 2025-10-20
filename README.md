# dkbparse
PDF parser for DKB bank and VISA statements.
Supports DKB statements post Summer 2023 (new format!).
Can format output for MoneyMoney.


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


## Limitations

The main limitation of this approach is that the output depends on the version of the installed `pdftotext` ([Poppler](https://poppler.freedesktop.org/)). Different results on different platforms can not be excluded.

New format not tested on Visa statements yet.
