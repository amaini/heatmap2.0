from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .forms import PurchaseLotForm, SectorForm, TickerForm
from .models import CachedQuote, PurchaseLot, Sector, Ticker, SiteConfig
from .services.finnhub import FinnhubClient, FinnhubError, Quote, compute_us_market_status


@login_required
@ensure_csrf_cookie
def index(request: HttpRequest) -> HttpResponse:
    return render(request, 'market/index.html', context={
        'FINNHUB_TIMEOUT_SECONDS': settings.FINNHUB_TIMEOUT_SECONDS,
    })


def _json_error(message: str, status: int = 400, code: str | None = None) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message, "code": code}, status=status)


@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def api_sectors(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        sectors = list(Sector.objects.all().values("id", "name"))
        return JsonResponse({"ok": True, "sectors": sectors})

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return _json_error("Invalid JSON body")

    if request.method == "POST":
        form = SectorForm(data)
        if form.is_valid():
            sector = form.save()
            return JsonResponse({"ok": True, "sector": {"id": sector.id, "name": sector.name}}, status=201)
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    if request.method == "PUT":
        sid = data.get("id")
        if not sid:
            return _json_error("Missing id")
        try:
            sector = Sector.objects.get(pk=sid)
        except Sector.DoesNotExist:
            return _json_error("Sector not found", 404)
        form = SectorForm(data, instance=sector)
        if form.is_valid():
            sector = form.save()
            return JsonResponse({"ok": True, "sector": {"id": sector.id, "name": sector.name}})
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    # DELETE
    sid = data.get("id")
    if not sid:
        return _json_error("Missing id")
    try:
        sector = Sector.objects.get(pk=sid)
    except Sector.DoesNotExist:
        return _json_error("Sector not found", 404)
    sector.delete()
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def api_tickers(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        qs = Ticker.objects.select_related("sector").annotate(
            lots_qty=Sum('lots__quantity'),
            lots_cost=Sum(ExpressionWrapper(F('lots__quantity') * F('lots__price'), output_field=DecimalField(max_digits=24, decimal_places=4)))
        )
        tid = request.GET.get("id")
        if tid:
            try:
                qs = qs.filter(pk=int(tid))
            except ValueError:
                return _json_error("Invalid id")
        tickers = []
        for t in qs:
            qty = float(t.lots_qty) if t.lots_qty is not None else None
            tot_cost = float(t.lots_cost) if t.lots_cost is not None else None
            avg_cost = (tot_cost / qty) if (qty and tot_cost is not None) else None
            tickers.append({
                "id": t.id,
                "symbol": t.symbol,
                "company_name": t.company_name,
                "security_type": t.security_type,
                "sector_id": t.sector_id,
                "sector__name": t.sector.name,
                "lots_qty": qty,
                "lots_cost": tot_cost,
                "avg_cost": avg_cost,
            })
        return JsonResponse({"ok": True, "tickers": tickers})

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return _json_error("Invalid JSON body")

    if request.method == "POST":
        form = TickerForm(data)
        if form.is_valid():
            ticker = form.save()
            return JsonResponse({
                "ok": True,
                "ticker": {
                    "id": ticker.id,
                    "symbol": ticker.symbol,
                    "company_name": ticker.company_name,
                    "security_type": ticker.security_type,
                    "sector_id": ticker.sector_id,
                    "sector__name": ticker.sector.name,
                }
            }, status=201)
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    if request.method == "PUT":
        tid = data.get("id")
        if not tid:
            return _json_error("Missing id")
        try:
            ticker = Ticker.objects.get(pk=tid)
        except Ticker.DoesNotExist:
            return _json_error("Ticker not found", 404)
        form = TickerForm(data, instance=ticker)
        if form.is_valid():
            ticker = form.save()
            return JsonResponse({
                "ok": True,
                "ticker": {
                    "id": ticker.id,
                    "symbol": ticker.symbol,
                    "company_name": ticker.company_name,
                    "security_type": ticker.security_type,
                    "sector_id": ticker.sector_id,
                    "sector__name": ticker.sector.name,
                }
            })
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    # DELETE
    tid = data.get("id")
    if not tid:
        return _json_error("Missing id")
    try:
        ticker = Ticker.objects.get(pk=tid)
    except Ticker.DoesNotExist:
        return _json_error("Ticker not found", 404)
    ticker.delete()
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def api_lots(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        ticker_id = request.GET.get("ticker_id")
        qs = PurchaseLot.objects.select_related("ticker")
        if ticker_id:
            qs = qs.filter(ticker_id=ticker_id)
        lots = list(qs.values("id", "ticker_id", "ticker__symbol", "quantity", "price", "trade_date", "notes"))
        return JsonResponse({"ok": True, "lots": lots})

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return _json_error("Invalid JSON body")

    if request.method == "POST":
        form = PurchaseLotForm(data)
        if form.is_valid():
            lot = form.save()
            return JsonResponse({
                "ok": True,
                "lot": {
                    "id": lot.id,
                    "ticker_id": lot.ticker_id,
                    "ticker__symbol": lot.ticker.symbol,
                    "quantity": str(lot.quantity),
                    "price": str(lot.price),
                    "trade_date": lot.trade_date.isoformat(),
                    "notes": lot.notes,
                }
            }, status=201)
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    if request.method == "PUT":
        lid = data.get("id")
        if not lid:
            return _json_error("Missing id")
        try:
            lot = PurchaseLot.objects.get(pk=lid)
        except PurchaseLot.DoesNotExist:
            return _json_error("Lot not found", 404)
        form = PurchaseLotForm(data, instance=lot)
        if form.is_valid():
            lot = form.save()
            return JsonResponse({
                "ok": True,
                "lot": {
                    "id": lot.id,
                    "ticker_id": lot.ticker_id,
                    "ticker__symbol": lot.ticker.symbol,
                    "quantity": str(lot.quantity),
                    "price": str(lot.price),
                    "trade_date": lot.trade_date.isoformat(),
                    "notes": lot.notes,
                }
            })
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    # DELETE
    lid = data.get("id")
    if not lid:
        return _json_error("Missing id")
    try:
        lot = PurchaseLot.objects.get(pk=lid)
    except PurchaseLot.DoesNotExist:
        return _json_error("Lot not found", 404)
    lot.delete()
    return JsonResponse({"ok": True})


@require_GET
def api_search(request: HttpRequest) -> JsonResponse:
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"ok": True, "results": []})
    client = FinnhubClient()
    try:
        results = client.search(q, exchange="US")
    except FinnhubError as e:
        return _json_error(str(e), status=e.status or 400, code=e.code)
    # Normalize fields
    normalized = []
    for r in results[:20]:
        normalized.append({
            "symbol": r.get("symbol") or r.get("displaySymbol") or "",
            "description": r.get("description") or r.get("name") or "",
            "type": r.get("type") or "",
        })
    return JsonResponse({"ok": True, "results": normalized})


@require_http_methods(["GET", "POST"])
def api_quotes(request: HttpRequest) -> JsonResponse:
    # Symbols from body or default to DB tickers
    symbols: List[str]
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            return _json_error("Invalid JSON body")
        symbols = data.get("symbols") or []
    else:
        symbols = []

    if not symbols:
        symbols = list(Ticker.objects.values_list("symbol", flat=True))

    client = FinnhubClient()
    quotes: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}
    now = timezone.now()

    for sym in symbols:
        try:
            q = client.quote(sym)
            quotes[sym] = {
                "c": q.c,
                "pc": q.pc,
                "h": q.h,
                "l": q.l,
                "dp": q.dp,
                "d": q.d,
                "t": q.t,
                "pre": q.pre,
                "post": q.post,
            }
            # 52-week metrics
            try:
                m = client.metrics(sym)
                quotes[sym].update({
                    "week52High": m.get("week52High"),
                    "week52Low": m.get("week52Low"),
                })
            except FinnhubError:
                pass
            # Persist cache for fallback
            CachedQuote.objects.update_or_create(
                symbol=sym,
                defaults={"data": quotes[sym]}
            )
        except FinnhubError as e:
            # Try cached fallback
            cached = CachedQuote.objects.filter(symbol=sym).first()
            if cached:
                quotes[sym] = cached.data
                errors[sym] = f"{e.code or 'ERROR'}: {e} (using cached)"
            else:
                errors[sym] = f"{e.code or 'ERROR'}: {e}"

    status = compute_us_market_status()
    payload = {
        "ok": True,
        "asOf": int(now.timestamp()),
        "marketStatus": status,
        "quotes": quotes,
        "errors": errors,
    }
    return JsonResponse(payload)


@require_GET
def api_market_status(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"ok": True, "status": compute_us_market_status()})


@require_http_methods(["GET", "POST", "PUT"]) 
def api_config(request: HttpRequest) -> JsonResponse:
    # Create or fetch single config row
    cfg, _ = SiteConfig.objects.get_or_create(id=1)
    if request.method == "GET":
        masked = cfg.masked_key()
        return JsonResponse({
            "ok": True,
            "config": {
                "hasKey": bool(cfg.finnhub_api_key.strip()),
                "masked": masked,
                "updated_at": int(cfg.updated_at.timestamp()) if cfg.updated_at else None,
            }
        })
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return _json_error("Invalid JSON body")
    new_key = (data.get("finnhub_api_key") or "").strip()
    cfg.finnhub_api_key = new_key
    cfg.save(update_fields=["finnhub_api_key", "updated_at"])
    return JsonResponse({"ok": True, "config": {"hasKey": bool(new_key), "masked": cfg.masked_key()}})
