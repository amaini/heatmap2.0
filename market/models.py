from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


class Sector(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        if not self.name:
            raise ValidationError({"name": "Sector name is required"})
        name = self.name.strip()
        if len(name) < 2:
            raise ValidationError({"name": "Sector name must be at least 2 characters"})
        self.name = name.title()

    def __str__(self) -> str:  # pragma: no cover
        return self.name


symbol_validator = RegexValidator(
    regex=r"^[A-Z][A-Z0-9\.\-]{0,9}$",
    message="Ticker symbol must be 1-10 chars, A-Z, digits, '.' or '-'",
)


class Ticker(models.Model):
    symbol = models.CharField(max_length=10, unique=True, validators=[symbol_validator])
    company_name = models.CharField(max_length=200, blank=True)
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name="tickers")
    security_type = models.CharField(
        max_length=50,
        default="Common Stock",
        help_text="Type of security, e.g., Common Stock",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["symbol"]

    def clean(self):
        super().clean()
        if not self.symbol:
            raise ValidationError({"symbol": "Symbol is required"})
        self.symbol = self.symbol.strip().upper()
        if len(self.symbol) > 10:
            raise ValidationError({"symbol": "Symbol too long"})
        symbol_validator(self.symbol)
        if self.company_name:
            self.company_name = self.company_name.strip()

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.symbol}"


class PurchaseLot(models.Model):
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name="lots")
    quantity = models.DecimalField(max_digits=20, decimal_places=4, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=20, decimal_places=4, validators=[MinValueValidator(0)])
    trade_date = models.DateField()
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trade_date", "-id"]

    def clean(self):
        super().clean()
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero"})
        if self.price is None or self.price < 0:
            raise ValidationError({"price": "Price must be zero or greater"})

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.ticker.symbol} {self.quantity}@{self.price} on {self.trade_date}"


class CachedQuote(models.Model):
    symbol = models.CharField(max_length=10)
    data = models.JSONField()
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["symbol"])]
        # Uniqueness enforced by migration-level UniqueConstraint
        

class SiteConfig(models.Model):
    finnhub_api_key = models.CharField(max_length=128, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def masked_key(self) -> str:
        k = (self.finnhub_api_key or "").strip()
        if not k:
            return ""
        if len(k) <= 6:
            return "***" + k[-2:]
        return k[:3] + "***" + k[-3:]
