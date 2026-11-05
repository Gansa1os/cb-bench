#!/usr/bin/env python3
import http.client, json, socket, ssl, sys, time, urllib.request

HOST = "api.cr.bot"
PATH_TP = "/v1/p2cMerchant/takePayment"
Headers = {
    "User-Agent": "Go-http-client/2.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
Body = b"{\"qr_id\":\"000000000000000000000000\"}"

def get_cf_trace():
    info = {}
    try:
        req = urllib.request.Request(f"https://{HOST}/cdn-cgi/trace", headers={"User-Agent": "Go-http-client/2.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            for line in r.read().decode("utf-8", "ignore").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k.strip()] = v.strip()
    except Exception:
        pass
    return info

def main():
    hostname = socket.gethostname()
    trace = get_cf_trace()
    ip = trace.get("ip", "unknown")
    loc = trace.get("loc", "?")
    colo = trace.get("colo", "?")

    # Measure TCP + TLS connect
    t0 = time.perf_counter()
    raw_sock = socket.create_connection((HOST, 443), timeout=5)
    t_tcp = (time.perf_counter() - t0) * 1000.0
    raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    ctx = ssl.create_default_context()
    t1 = time.perf_counter()
    tls_sock = ctx.wrap_socket(raw_sock, server_hostname=HOST)
    t_tls = (time.perf_counter() - t1) * 1000.0
    tls_sock.close()

    # Persistent HTTPS keep-alive session to CryptoBot Origin
    conn = http.client.HTTPSConnection(HOST, 443, timeout=6, context=ctx)
    t0 = time.perf_counter()
    conn.request("POST", PATH_TP, body=Body, headers=Headers)
    resp = conn.getresponse()
    cold_ms = (time.perf_counter() - t0) * 1000.0
    resp.read()

    warm_fast = []
    for _ in range(12):
        time.sleep(0.12)
        t0 = time.perf_counter()
        conn.request("POST", PATH_TP, body=Body, headers=Headers)
        r = conn.getresponse()
        ms = (time.perf_counter() - t0) * 1000.0
        r.read()
        warm_fast.append(ms)

    warm_1s = []
    for _ in range(5):
        time.sleep(1.0)
        t0 = time.perf_counter()
        conn.request("POST", PATH_TP, body=Body, headers=Headers)
        r = conn.getresponse()
        ms = (time.perf_counter() - t0) * 1000.0
        r.read()
        warm_1s.append(ms)

    conn.close()
    warm_fast.sort()
    warm_1s.sort()
    res = {
        "host": hostname,
        "ip": ip,
        "loc": loc,
        "cf_colo": colo,
        "tcp_ms": round(t_tcp, 1),
        "tls_ms": round(t_tls, 1),
        "cold_ms": round(cold_ms, 1),
        "warm_min_ms": round(warm_fast[0], 1),
        "warm_p10_ms": round(warm_fast[1], 1),
        "warm_p50_ms": round(warm_fast[len(warm_fast)//2], 1),
        "warm_avg_ms": round(sum(warm_fast)/len(warm_fast), 1),
        "idle1s_p50_ms": round(warm_1s[len(warm_1s)//2], 1),
    }
    print("CB_BENCH_JSON:" + json.dumps(res))

if __name__ == "__main__":
    main()
