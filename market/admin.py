from django.contrib import admin
from .models import Sector, Ticker, PurchaseLot, CachedQuote


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Ticker)
class TickerAdmin(admin.ModelAdmin):
    list_display = ("symbol", "company_name", "sector", "security_type", "created_at")
    list_filter = ("sector", "security_type")
    search_fields = ("symbol", "company_name")


@admin.register(PurchaseLot)
class PurchaseLotAdmin(admin.ModelAdmin):
    list_display = ("ticker", "quantity", "price", "trade_date", "created_at")
    list_filter = ("ticker",)
    search_fields = ("ticker__symbol",)


@admin.register(CachedQuote)
class CachedQuoteAdmin(admin.ModelAdmin):
    list_display = ("symbol", "fetched_at")
    search_fields = ("symbol",)

