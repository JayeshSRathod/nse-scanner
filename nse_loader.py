"""
nse_loader.py — REPLACE ONLY the load_day() function
======================================================
Everything else in your file stays exactly as-is.
Find 'def load_day(' and replace the entire function
(from 'def load_day' to the next 'def' or section break)
with this clean version.
"""

def load_day(trade_date, do_cleanup=False):
    fmt    = trade_date.strftime("%Y/%m/%d")
    folder = os.path.join(SAVE_ROOT, fmt)
    result = {"date": trade_date, "status": "ok", "rows": {}, "skipped": [], "errors": []}

    print(f"\n{'='*56}")
    print(f"  Loading: {trade_date.strftime('%d-%b-%Y')}  ({trade_date.strftime('%A')})")
    print(f"{'='*56}")

    if not os.path.exists(folder):
        print(f"  SKIP  Folder not found: {folder}")
        result["status"] = "skip"
        return result

    conn = get_db()
    already = conn.execute(
        "SELECT date FROM load_log WHERE date=? AND status='ok'",
        [trade_date.isoformat()]).fetchone()
    if already:
        print(f"  Already loaded -- skipping (use --force to reload)")
        conn.close()
        result["status"] = "already_loaded"
        return result

    parsed  = parse_all(folder, trade_date)
    notes   = []
    log_row = {
        "date": trade_date.isoformat(), "loaded_at": datetime.now().isoformat(),
        "prices_rows": 0, "blacklist_rows": 0, "index_rows": 0,
        "vol_rows": 0, "week52_rows": 0, "pe_rows": 0,
        "status": "ok", "notes": ""
    }

    # 1 -- Prices (REQUIRED)
    ok, reason = validate("bhavdata", parsed["bhavdata"], trade_date)
    if ok:
        n = load_prices(conn, parsed["bhavdata"], trade_date)
        log_row["prices_rows"] = n
        result["rows"]["prices"] = n
        print(f"  OK    daily_prices    : {n} rows inserted")
    else:
        msg = f"Prices FAILED: {reason}"
        print(f"  FAIL  daily_prices    : {reason}")
        result["errors"].append(msg)
        result["status"] = "partial"
        log_row["status"] = "partial"
        notes.append(msg)

    # 2 -- Blacklist (REQUIRED)
    ok, reason = validate("blacklist", parsed["blacklist"], trade_date)
    if ok:
        n = load_blacklist(conn, parsed["blacklist"], trade_date)
        log_row["blacklist_rows"] = len(parsed["blacklist"])
        result["rows"]["blacklist"] = n
        print(f"  OK    blacklist       : {len(parsed['blacklist'])} symbols ({n} new)")
    else:
        print(f"  SKIP  blacklist       : {reason}")
        result["skipped"].append("blacklist")
        notes.append(f"blacklist: {reason}")

    # 3 -- Index (REQUIRED)
    ok, reason = validate("ind_close", parsed["ind_close"], trade_date)
    if ok:
        n = load_index(conn, parsed["ind_close"], trade_date)
        log_row["index_rows"] = n
        result["rows"]["index_perf"] = n
        print(f"  OK    index_perf      : {n} indices inserted")
    else:
        print(f"  SKIP  index_perf      : {reason}")
        result["skipped"].append("index_perf")
        notes.append(f"index: {reason}")

    # 4 -- Volatility (OPTIONAL)
    ok, reason = validate("volatility", parsed["volatility"], trade_date)
    if ok:
        n = load_vol(conn, parsed["volatility"], trade_date)
        log_row["vol_rows"] = n
        result["rows"]["volatility"] = n
        print(f"  OK    volatility      : {n} rows inserted")
    else:
        print(f"  SKIP  volatility      : not available (add bundle ZIP)")

    # 5 -- 52W (OPTIONAL)
    ok, reason = validate("week52", parsed["week52"], trade_date)
    if ok:
        n = load_w52(conn, parsed["week52"], trade_date)
        log_row["week52_rows"] = n
        result["rows"]["week52"] = n
        print(f"  OK    week52          : {n} rows inserted")
    else:
        print(f"  SKIP  week52          : not available (add bundle ZIP)")

    # Week52 health check for category system
    w52_recent = conn.execute(
        "SELECT COUNT(*) FROM week52 WHERE date >= ?",
        [(trade_date - timedelta(days=7)).isoformat()]
    ).fetchone()[0]
    if w52_recent == 0:
        print(f"  ⚠️   week52 EMPTY — '🔝 Close to Peak' category won't work")
        print(f"       Download bundle ZIP from NSE for full categories")
        notes.append("week52 empty — peak category disabled")

    # 6 -- PE (OPTIONAL)
    ok, reason = validate("pe", parsed["pe"], trade_date)
    if ok:
        n = load_pe(conn, parsed["pe"], trade_date)
        log_row["pe_rows"] = n
        result["rows"]["pe"] = n
        print(f"  OK    pe_ratios       : {n} rows inserted")
    else:
        print(f"  SKIP  pe_ratios       : not available (add bundle ZIP)")

    log_row["notes"] = " | ".join(notes)
    conn.execute("""INSERT OR REPLACE INTO load_log
        (date,loaded_at,prices_rows,blacklist_rows,index_rows,
         vol_rows,week52_rows,pe_rows,status,notes)
        VALUES (:date,:loaded_at,:prices_rows,:blacklist_rows,:index_rows,
                :vol_rows,:week52_rows,:pe_rows,:status,:notes)""", log_row)
    conn.commit()
    conn.close()

    if do_cleanup and result["status"] != "skip":
        deleted = cleanup_day(folder)
        if deleted:
            print(f"  Cleanup: deleted {len(deleted)} large files")

    total = sum(result["rows"].values())
    print(f"  Summary: {total} rows | {len(result['skipped'])} skipped | status={result['status']}")
    log.info(f"Loaded {trade_date}: {total} rows, status={result['status']}")
    return result
