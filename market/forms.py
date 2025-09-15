from __future__ import annotations

from django import forms
from .models import Sector, Ticker, PurchaseLot, symbol_validator


class SectorForm(forms.ModelForm):
    class Meta:
        model = Sector
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip().title()
        if len(name) < 2:
            raise forms.ValidationError("Sector name must be at least 2 characters")
        # Enforce case-insensitive uniqueness, exclude self on update
        qs = Sector.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Sector with this name already exists")
        return name


class TickerForm(forms.ModelForm):
    class Meta:
        model = Ticker
        fields = ["symbol", "company_name", "sector", "security_type"]

    def clean_symbol(self):
        symbol = self.cleaned_data["symbol"].strip().upper()
        symbol_validator(symbol)
        # Enforce uniqueness
        qs = Ticker.objects.filter(symbol__iexact=symbol)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ticker with this symbol already exists")
        return symbol


class PurchaseLotForm(forms.ModelForm):
    class Meta:
        model = PurchaseLot
        fields = ["ticker", "quantity", "price", "trade_date", "notes"]
