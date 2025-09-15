from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import time

from django.core.management.base import BaseCommand
from django.db import transaction

from market.models import Sector, Ticker, PurchaseLot, CachedQuote


class Command(BaseCommand):
    help = "Seed the database with demo sectors, tickers, purchase lots, and cached quotes"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding demo data…"))

        # Sectors
        sector_names = [
            "Technology", "Financials", "Healthcare", "Consumer Discretionary",
            "Energy", "Industrials", "Communication Services", "Utilities",
            "Materials", "Real Estate",
        ]
        sectors = {}
        for name in sector_names:
            s, _ = Sector.objects.get_or_create(name=name)
            sectors[name] = s
        self.stdout.write(self.style.SUCCESS(f"Created/ensured {len(sectors)} sectors"))

        # Tickers (symbol, name, sector)
        ticker_specs = [
            ("AAPL", "Apple Inc.", "Technology"),
            ("MSFT", "Microsoft Corporation", "Technology"),
            ("GOOGL", "Alphabet Inc. (Class A)", "Technology"),
            ("NVDA", "NVIDIA Corporation", "Technology"),
            ("META", "Meta Platforms, Inc.", "Technology"),
            ("AMZN", "Amazon.com, Inc.", "Consumer Discretionary"),
            ("TSLA", "Tesla, Inc.", "Consumer Discretionary"),
            ("JPM", "JPMorgan Chase & Co.", "Financials"),
            ("BAC", "Bank of America Corporation", "Financials"),
            ("JNJ", "Johnson & Johnson", "Healthcare"),
            ("PFE", "Pfizer Inc.", "Healthcare"),
            ("UNH", "UnitedHealth Group Incorporated", "Healthcare"),
            ("XOM", "Exxon Mobil Corporation", "Energy"),
            ("CVX", "Chevron Corporation", "Energy"),
            ("BA", "The Boeing Company", "Industrials"),
            ("CAT", "Caterpillar Inc.", "Industrials"),
            ("T", "AT&T Inc.", "Communication Services"),
            ("VZ", "Verizon Communications Inc.", "Communication Services"),
            ("NEE", "NextEra Energy, Inc.", "Utilities"),
            ("DUK", "Duke Energy Corporation", "Utilities"),
            ("LIN", "Linde plc", "Materials"),
            ("NUE", "Nucor Corporation", "Materials"),
            ("AMT", "American Tower Corporation", "Real Estate"),
            ("PLD", "Prologis, Inc.", "Real Estate"),
        ]

        tickers = {}
        for sym, cname, sname in ticker_specs:
            t, created = Ticker.objects.get_or_create(symbol=sym, defaults={
                'company_name': cname,
                'sector': sectors[sname],
                'security_type': 'Common Stock',
            })
            if not created:
                # ensure sector/name synced for existing records
                changed = False
                if t.company_name != cname:
                    t.company_name = cname; changed = True
                if t.sector_id != sectors[sname].id:
                    t.sector = sectors[sname]; changed = True
                if changed:
                    t.save(update_fields=['company_name', 'sector'])
            tickers[sym] = t
        self.stdout.write(self.style.SUCCESS(f"Created/ensured {len(tickers)} tickers"))

        # Lots - a few per some tickers
        lots_plan = [
            ("AAPL", [(Decimal('10'), Decimal('150'), 20), (Decimal('5'), Decimal('165'), 10)]),
            ("MSFT", [(Decimal('8'), Decimal('300'), 35)]),
            ("AMZN", [(Decimal('3'), Decimal('120'), 60), (Decimal('2.5'), Decimal('130'), 15)]),
            ("TSLA", [(Decimal('1.2'), Decimal('700'), 200)]),
            ("JPM", [(Decimal('20'), Decimal('120'), 90)]),
            ("XOM", [(Decimal('15'), Decimal('105'), 25)]),
        ]
        today = date.today()
        created_lots = 0
        for sym, entries in lots_plan:
            t = tickers.get(sym)
            if not t:
                continue
            for qty, price, days_ago in entries:
                trade_date = today - timedelta(days=int(days_ago))
                PurchaseLot.objects.get_or_create(
                    ticker=t, quantity=qty, price=price, trade_date=trade_date,
                    defaults={'notes': 'Seed lot'}
                )
                created_lots += 1
        self.stdout.write(self.style.SUCCESS(f"Created/ensured {created_lots} purchase lots"))

        # Cached quotes - simple, consistent values
        def put_quote(symbol: str, c: float, pc: float, h: float, l: float):
            dp = ((c - pc) / pc) * 100 if pc else None
            d = (c - pc) if pc else None
            data = {
                'c': round(c, 2), 'pc': round(pc, 2), 'h': round(h, 2), 'l': round(l, 2),
                'dp': round(dp, 2) if dp is not None else None,
                'd': round(d, 2) if d is not None else None,
                't': int(time.time()), 'pre': None, 'post': None,
            }
            CachedQuote.objects.update_or_create(symbol=symbol, defaults={'data': data})

        sample_quotes = {
            'AAPL': (182.11, 180.22, 184.50, 178.90),
            'MSFT': (412.33, 410.10, 415.20, 405.80),
            'GOOGL': (142.05, 143.20, 144.00, 140.10),
            'NVDA': (912.88, 900.00, 930.00, 888.00),
            'META': (505.12, 500.00, 510.00, 492.00),
            'AMZN': (176.45, 175.80, 178.50, 172.20),
            'TSLA': (178.20, 182.00, 185.00, 175.00),
            'JPM': (195.40, 194.70, 197.00, 192.50),
            'XOM': (120.15, 118.60, 121.00, 117.80),
            'CVX': (160.70, 159.90, 162.20, 158.10),
        }
        for sym, vals in sample_quotes.items():
            put_quote(sym, *vals)
        self.stdout.write(self.style.SUCCESS(f"Created/updated cached quotes for {len(sample_quotes)} symbols"))

        self.stdout.write(self.style.SUCCESS("Demo data ready."))

