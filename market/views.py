from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    now = timezone.now()
    now_ts = int(now.timestamp())

    metrics_ttl = getattr(settings, "FINNHUB_METRICS_TTL_SECONDS", 21600)
    try:
        metrics_ttl = int(metrics_ttl)
    except (TypeError, ValueError):
        metrics_ttl = 21600

    max_workers = getattr(settings, "FINNHUB_MAX_CONCURRENCY", 4)
    try:
        max_workers = int(max_workers)
    except (TypeError, ValueError):
        max_workers = 4
    if max_workers < 1:
        max_workers = 1

    cached_entries = {c.symbol: c for c in CachedQuote.objects.filter(symbol__in=symbols)}

    quote_ttl = getattr(settings, "FINNHUB_QUOTE_TTL_SECONDS", 10)
    try:
        quote_ttl = int(quote_ttl)
    except (TypeError, ValueError):
        quote_ttl = 10
    if quote_ttl < 0:
        quote_ttl = 0

    fresh_cached: Dict[str, Dict[str, Any]] = {}
    symbols_to_fetch: List[str] = []
    for sym in symbols:
        cached = cached_entries.get(sym)
        use_cache = False
        if cached and quote_ttl > 0 and cached.fetched_at:
            try:
                age = (now - cached.fetched_at).total_seconds()
            except Exception:
                age = None
            if age is not None and age < quote_ttl:
                cached_payload = cached.data if isinstance(cached.data, dict) else {}
                if cached_payload:
                    fresh_cached[sym] = dict(cached_payload)
                    use_cache = True
        if not use_cache:
            symbols_to_fetch.append(sym)

    quotes: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, str] = {}

    quote_results: Dict[str, Quote] = {}
    quote_errors: Dict[str, FinnhubError | Exception] = {}

    def format_error(exc: FinnhubError | Exception) -> str:
        if isinstance(exc, FinnhubError):
            prefix = exc.code or "ERROR"
            return f"{prefix}: {exc}"
        return str(exc)

    if symbols_to_fetch:
        worker_count = min(max_workers, len(symbols_to_fetch))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {executor.submit(client.quote, sym): sym for sym in symbols_to_fetch}
            for future in as_completed(future_map):
                sym = future_map[future]
                try:
                    quote_results[sym] = future.result()
                except FinnhubError as exc:
                    quote_errors[sym] = exc
                except Exception as exc:
                    quote_errors[sym] = FinnhubError(str(exc))

    metrics_symbols: List[str] = []
    if metrics_ttl <= 0:
        metrics_symbols = [sym for sym in symbols if sym not in quote_errors]
    else:
        for sym in symbols:
            if sym in quote_errors:
                continue
            cached = cached_entries.get(sym)
            cached_data = cached.data if cached else {}
            raw_ts = None
            if cached_data:
                raw_ts = cached_data.get("metricsAsOf") or cached_data.get("metrics_as_of")
            metrics_ts = None
            if raw_ts is not None:
                try:
                    metrics_ts = int(float(raw_ts))
                except (TypeError, ValueError):
                    metrics_ts = None
            if metrics_ts is None or (now_ts - metrics_ts) >= metrics_ttl:
                metrics_symbols.append(sym)

    metrics_results: Dict[str, Dict[str, Any]] = {}
    metrics_errors: Dict[str, FinnhubError] = {}
    if metrics_symbols:
        worker_count = min(max_workers, len(metrics_symbols))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {executor.submit(client.metrics, sym): sym for sym in metrics_symbols}
            for future in as_completed(future_map):
                sym = future_map[future]
                try:
                    metrics_results[sym] = future.result()
                except FinnhubError as exc:
                    metrics_errors[sym] = exc
                except Exception as exc:
                    metrics_errors[sym] = FinnhubError(str(exc))

    for sym in symbols:
        cached = cached_entries.get(sym)
        cached_data = cached.data if cached and isinstance(cached.data, dict) else {}
        quote_obj = quote_results.get(sym)
        if quote_obj:
            payload = {
                "c": quote_obj.c,
                "pc": quote_obj.pc,
                "h": quote_obj.h,
                "l": quote_obj.l,
                "dp": quote_obj.dp,
                "d": quote_obj.d,
                "t": quote_obj.t,
                "pre": quote_obj.pre,
                "post": quote_obj.post,
            }
            metrics_payload = metrics_results.get(sym)
            if metrics_payload:
                payload.update({
                    "week52High": metrics_payload.get("week52High"),
                    "week52Low": metrics_payload.get("week52Low"),
                    "metricsAsOf": now_ts,
                })
            else:
                if cached_data:
                    if "week52High" in cached_data:
                        payload["week52High"] = cached_data.get("week52High")
                    if "week52Low" in cached_data:
                        payload["week52Low"] = cached_data.get("week52Low")
                    if "metricsAsOf" in cached_data:
                        payload["metricsAsOf"] = cached_data.get("metricsAsOf")
            quotes[sym] = payload
            CachedQuote.objects.update_or_create(symbol=sym, defaults={"data": payload})
            if sym in metrics_errors:
                errors[sym] = f"{format_error(metrics_errors[sym])} (kept cached metrics)"
            continue

        if sym in fresh_cached:
            payload = dict(fresh_cached.get(sym, {}))
            metrics_payload = metrics_results.get(sym)
            if metrics_payload:
                payload.update({
                    "week52High": metrics_payload.get("week52High"),
                    "week52Low": metrics_payload.get("week52Low"),
                    "metricsAsOf": now_ts,
                })
                if cached:
                    CachedQuote.objects.filter(symbol=sym).update(data=payload)
            quotes[sym] = payload
            if sym in metrics_errors:
                errors[sym] = f"{format_error(metrics_errors[sym])} (kept cached metrics)"
            continue

        if cached_data:
            quotes[sym] = cached_data
            if sym in quote_errors:
                errors[sym] = f"{format_error(quote_errors[sym])} (using cached)"
        elif sym in quote_errors:
            errors[sym] = format_error(quote_errors[sym])

    status = compute_us_market_status()
    payload = {
        "ok": True,
        "asOf": now_ts,
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
