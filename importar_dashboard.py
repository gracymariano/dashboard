#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automação de Importação — Guardar Dinheiro Dashboard
Lê os CSVs da pasta Automação e atualiza o Supabase no formato
exato que o dashboard espera.

Estrutura de pastas:
  Automação/<Site>/<Ano>/<Mês>/analytics/top páginas/YYYY_MM_DD_*.csv
  Automação/<Site>/<Ano>/<Mês>/analytics/tráfego/YYYY_MM_DD_*.csv
  Automação/<Site>/<Ano>/<Mês>/analytics/usuários/YYYY_MM_DD_*.csv
  Automação/<Site>/<Ano>/<Mês>/analytics/origem de campanha/YYYY_MM_DD_*.csv
  Automação/<Site>/<Ano>/<Mês>/search_console/gráfico/YYYY_MM_DD_*.csv
  Automação/<Site>/<Ano>/<Mês>/search_console/oportunidades/YYYY_MM_DD_Consultas.csv
  Automação/<Site>/<Ano>/<Mês>/search_console/segmentos/YYYY_MM_DD_*.csv

  O prefixo YYYY_MM_DD_ é opcional — arquivos sem prefixo continuam funcionando.
  Quando houver múltiplos arquivos na mesma pasta, o mais recente (pela data no nome)
  é importado e os anteriores são mantidos como histórico.
"""

import os, csv, json, sys, re
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    print("Instalando dependência 'requests'...")
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

# ══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════

BASE_DIR = Path(r"C:\Users\greka\OneDrive\Desktop\Automação")

SB_URL = "https://qmvypslzwxxltqeidpoq.supabase.co"
SB_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
           "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFtdnlwc2x6d3h4bHRxZWlkcG9xIiwicm9sZSI6ImFub24i"
           "LCJpYXQiOjE3Nzk1MDY1ODAsImV4cCI6MjA5NTA4MjU4MH0."
           "LpTPOTTIXN-QSCEgUVC4xmZvBteuSTYmMYltTptCKVU")
SB_HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type": "application/json",
}

# Pasta → chave do prop no dashboard
SITE_MAP = {
    "guardar dinheiro":     "gd",
    "blog guardar dinheiro":"blog",
    "app guardar dinheiro": "app",
    "cora cora news":       "cora",
    "receitascom":          "rec",
    "savemoney":            "save",
    "check-in do amor":     "cia",
    "gracy.mariano":        "gracy",
    "turistandosemgrana":   "tsg",
}

# Nome do mês → (índice no array MO do dashboard, índice calendário 0-11)
# MO array: Maio=0, Junho=1, Julho=2, Agosto=3, Setembro=4, Outubro=5, Novembro=6
MONTH_MAP = {
    "janeiro":   {"mo_idx": None, "cal_idx": 0},
    "fevereiro": {"mo_idx": None, "cal_idx": 1},
    "março":     {"mo_idx": None, "cal_idx": 2},
    "marco":     {"mo_idx": None, "cal_idx": 2},
    "abril":     {"mo_idx": None, "cal_idx": 3},
    "maio":      {"mo_idx": 0,    "cal_idx": 4},
    "junho":     {"mo_idx": 1,    "cal_idx": 5},
    "julho":     {"mo_idx": 2,    "cal_idx": 6},
    "agosto":    {"mo_idx": 3,    "cal_idx": 7},
    "setembro":  {"mo_idx": 4,    "cal_idx": 8},
    "outubro":   {"mo_idx": 5,    "cal_idx": 9},
    "novembro":  {"mo_idx": 6,    "cal_idx": 10},
    "dezembro":  {"mo_idx": None, "cal_idx": 11},
}

# Canal GA4 → chave do dashboard
CHANNEL_MAP = {
    "organic search":   "organic_search",
    "busca orgânica":   "organic_search",
    "direct":           "direct",
    "direto":           "direct",
    "unassigned":       "unassigned",
    "não atribuído":    "unassigned",
    "nao atribuido":    "unassigned",
    "referral":         "referral",
    "referência":       "referral",
    "organic social":   "organic_social",
    "social orgânico":  "organic_social",
    "paid search":      "paid_search",
    "busca paga":       "paid_search",
    "organic video":    "organic_video",
    "vídeo orgânico":   "organic_video",
    "email":            "email",
    "e-mail":           "email",
    "outros":           "outros",
    "other":            "outros",
    "(other)":          "outros",
    "ai assistant":     "outros",
    "cross-network":    "outros",
}

# Métricas por seção para garantir arrays[12]
SECTION_METRICS = {
    "traf": ["sessoes_tot", "sessoes_eng", "tx_eng", "tempo_sessao", "ev_sessao"],
    "user": ["usuarios_tot", "novos", "recorrentes", "tempo_usuario", "sessoes_eng"],
    "gsc":  ["cliques", "impressoes", "ctr", "posicao"],
}


# ══════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════

def arr12():
    return [None] * 12


_DATE_PAT = re.compile(r'^(\d{4}_\d{2}_\d{2})_')


def latest_csv(folder: Path):
    """
    Retorna o CSV mais recente de uma pasta, priorizando arquivos com prefixo
    de data no formato YYYY_MM_DD_*.csv (ex: 2026_06_15_trafego.csv).
    Se nenhum tiver prefixo de data, retorna o último em ordem alfabética.
    Retorna None se a pasta não existir ou não tiver CSVs.
    """
    if not folder.exists():
        return None
    dated, undated = [], []
    for f in folder.glob("*.csv"):
        m = _DATE_PAT.match(f.name)
        if m:
            dated.append((m.group(1), f))
        else:
            undated.append(f)
    if dated:
        dated.sort(key=lambda x: x[0], reverse=True)
        return dated[0][1]
    if undated:
        return sorted(undated)[-1]
    return None


def latest_csv_multi(folder: Path):
    """
    Para pastas com múltiplos CSVs de tipos diferentes (ex: segmentos).
    Retorna todos os CSVs da data mais recente.
    Se nenhum tiver prefixo de data, retorna todos os CSVs.
    """
    if not folder.exists():
        return []
    dated: dict = {}
    undated = []
    for f in folder.glob("*.csv"):
        m = _DATE_PAT.match(f.name)
        if m:
            dated.setdefault(m.group(1), []).append(f)
        else:
            undated.append(f)
    if dated:
        latest_date = sorted(dated.keys(), reverse=True)[0]
        return sorted(dated[latest_date])
    return sorted(undated)


def latest_csv_named(folder: Path, base_name: str):
    """
    Busca o arquivo mais recente que termine com `base_name` (ex: Consultas.csv).
    Suporta tanto nome exato quanto YYYY_MM_DD_base_name.
    """
    if not folder.exists():
        return None
    candidates = []
    base_lower = base_name.lower()
    for f in folder.glob("*.csv"):
        m = _DATE_PAT.match(f.name)
        if m:
            rest = f.name[len(m.group(0)):]
            if rest.lower() == base_lower:
                candidates.append((m.group(1), f))
        elif f.name.lower() == base_lower:
            candidates.append(("", f))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def read_csv_file(filepath):
    """Lê CSV ignorando linhas de comentário (#) e BOM. Retorna list of lists."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(filepath, encoding=enc, newline="") as f:
                content = f.read()
            break
        except (UnicodeDecodeError, OSError):
            continue
    else:
        print(f"    ⚠ Não foi possível ler: {filepath.name}")
        return []

    content = content.lstrip("﻿")
    lines = [
        l for l in content.splitlines()
        if l.strip() and not l.strip().startswith("#") and l.strip() != '""'
    ]
    if not lines:
        return []

    return list(csv.reader(lines))


def parse_num(val):
    """Converte string de número para float.
    - Valor com '%' no final → divide por 100
    - Outros → float direto
    """
    if val is None:
        return None
    v = str(val).replace('"', '').strip()
    if not v or v in ("-", "—"):
        return None
    try:
        if v.endswith("%"):
            return float(v.rstrip("%")) / 100
        # Remove separador de milhar (vírgula) mantendo ponto decimal
        v_clean = v.replace(",", "")
        return float(v_clean)
    except ValueError:
        return None


def find_col(headers, keywords):
    """Índice da coluna cujo header contém alguma das keywords (case-insensitive)."""
    for i, h in enumerate(headers):
        hl = h.lower().replace('"', '').strip()
        for kw in keywords:
            if kw in hl:
                return i
    return -1


def weighted_avg(pairs):
    """Média ponderada de [(valor, peso), ...]."""
    num = sum(v * w for v, w in pairs if v is not None and w is not None and w > 0)
    den = sum(w for v, w in pairs if v is not None and w is not None and w > 0)
    return num / den if den else None


def ensure_an_data(an, year, section, prop):
    """Garante ac.an.data[year][section][prop] com arrays[12]."""
    an.setdefault("data", {})
    an["data"].setdefault(year, {})
    an["data"][year].setdefault(section, {})
    if prop not in an["data"][year][section]:
        an["data"][year][section][prop] = {}
    d = an["data"][year][section][prop]
    for mk in SECTION_METRICS.get(section, []):
        if not isinstance(d.get(mk), list) or len(d[mk]) != 12:
            d[mk] = arr12()
    return d


# ══════════════════════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════════════════════

def sb_get(key):
    url = f"{SB_URL}/rest/v1/dashboard_state?key=eq.{key}&select=value"
    r = requests.get(url, headers=SB_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data[0]["value"] if data else None


def sb_set(key, value):
    url = f"{SB_URL}/rest/v1/dashboard_state"
    payload = {
        "key": key,
        "value": value,
        "updated_at": datetime.utcnow().isoformat(),
    }
    r = requests.post(
        url,
        headers={**SB_HEADERS, "Prefer": "resolution=merge-duplicates"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()


# ══════════════════════════════════════════════════════════════
# PARSERS
# ══════════════════════════════════════════════════════════════

def parse_top_pages(filepath):
    """GA4 Páginas e Telas → [{n, cur, prev}, ...]"""
    rows = read_csv_file(filepath)
    if not rows:
        return []

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    path_idx = find_col(hdrs, [
        "caminho da p", "page path", "título da página", "titulo da pagina",
        "página e classe", "pagina e classe", "screen class", "page title",
    ])
    if path_idx < 0:
        path_idx = 0  # fallback: primeira coluna

    sess_idx = find_col(hdrs, [
        "visualiz", "views", "sessõe", "sessoe", "session", "exib",
    ])
    if sess_idx < 0:
        sess_idx = 1

    result = []
    for row in rows[1:]:
        if len(row) <= max(path_idx, sess_idx):
            continue
        name = row[path_idx].replace('"', '').strip()
        skip_vals = {"total", "totais", "(not set)", "(not provided)", ""}
        if not name or name.lower() in skip_vals:
            continue
        val = parse_num(row[sess_idx])
        if val is None or val == 0:
            continue
        result.append({"n": name, "cur": int(val), "prev": 0})

    result.sort(key=lambda x: x["cur"], reverse=True)
    return result


def parse_trafego(filepath):
    """GA4 Aquisição de Tráfego → totais (traf) + por canal (aquis)."""
    rows = read_csv_file(filepath)
    if not rows:
        return None

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    sess_idx     = find_col(hdrs, ["sessõe", "sessoe", "session"])
    sess_eng_idx = find_col(hdrs, ["sessões engaj", "sessoes engaj", "engaged session"])
    tx_eng_idx   = find_col(hdrs, ["taxa de engaj", "engagement rate"])
    tempo_idx    = find_col(hdrs, ["tempo médio de engajamento por sess",
                                    "tempo medio de engajamento por sess",
                                    "average engagement time per session"])
    ev_sess_idx  = find_col(hdrs, ["eventos por sess", "events per session"])

    if sess_idx < 0:
        print(f"    ⚠ Coluna 'Sessões' não encontrada em {filepath.name}")
        return None

    data_rows = []
    for row in rows[1:]:
        if not row:
            continue
        chan = row[0].replace('"', '').strip()
        if not chan or chan.lower() in ("total", "totais"):
            continue

        def get(idx):
            return parse_num(row[idx]) if 0 <= idx < len(row) else None

        sess = get(sess_idx) or 0
        data_rows.append({
            "chan":     chan,
            "sess":     sess,
            "sess_eng": get(sess_eng_idx) or 0,
            "tx_eng":   get(tx_eng_idx),
            "tempo":    get(tempo_idx),
            "ev_sess":  get(ev_sess_idx),
        })

    if not data_rows:
        return None

    total_sess     = sum(r["sess"] for r in data_rows)
    total_sess_eng = sum(r["sess_eng"] for r in data_rows)

    traf = {
        "sessoes_tot":  total_sess,
        "sessoes_eng":  total_sess_eng,
        "tx_eng":       weighted_avg([(r["tx_eng"],  r["sess"]) for r in data_rows]),
        "tempo_sessao": weighted_avg([(r["tempo"],   r["sess"]) for r in data_rows]),
        "ev_sessao":    weighted_avg([(r["ev_sess"], r["sess"]) for r in data_rows]),
    }

    # Por canal → aquis histórico
    aquis = {}
    for r in data_rows:
        key = CHANNEL_MAP.get(r["chan"].lower())
        if key:
            aquis[key] = aquis.get(key, 0) + r["sess"]
        else:
            aquis["outros"] = aquis.get("outros", 0) + r["sess"]

    return {"traf": traf, "aquis": aquis}


def parse_usuarios(filepath):
    """GA4 Aquisição de Usuários → métricas agregadas (user)."""
    rows = read_csv_file(filepath)
    if not rows:
        return None

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    usu_idx   = find_col(hdrs, ["total de usuá", "total de usu", "total users"])
    novos_idx = find_col(hdrs, ["novos usuá", "novos usu", "new users"])
    rec_idx   = find_col(hdrs, ["recorrent", "returning"])
    tempo_idx = find_col(hdrs, ["tempo médio de engajamento por usuário",
                                 "tempo medio de engajamento por usuario",
                                 "average engagement time per active user"])
    sess_eu_idx = find_col(hdrs, ["sessões engajadas por usuário",
                                   "sessoes engajadas por usuario",
                                   "engaged sessions per"])

    # Fallback genérico
    if usu_idx < 0:
        usu_idx = find_col(hdrs, ["usuários", "usuarios", "users"])
    if usu_idx < 0:
        usu_idx = 1

    tot_usu = tot_novos = tot_rec = 0
    wp_tempo, wp_sess_eu = [], []

    for row in rows[1:]:
        if not row:
            continue
        chan = row[0].replace('"', '').strip().lower()
        if chan in ("total", "totais"):
            continue

        def get(idx):
            return parse_num(row[idx]) if 0 <= idx < len(row) else None

        usu = int(get(usu_idx) or 0)
        if usu == 0:
            continue

        tot_usu   += usu
        tot_novos += int(get(novos_idx) or 0)
        tot_rec   += int(get(rec_idx)   or 0)

        v = get(tempo_idx)
        if v is not None:
            wp_tempo.append((v, usu))

        v = get(sess_eu_idx)
        if v is not None:
            wp_sess_eu.append((v, usu))

    if tot_usu == 0:
        return None

    return {
        "usuarios_tot":  tot_usu   or None,
        "novos":         tot_novos or None,
        "recorrentes":   tot_rec   or None,
        "tempo_usuario": weighted_avg(wp_tempo),
        "sessoes_eng":   weighted_avg(wp_sess_eu),
    }


def parse_campanha(filepath):
    """GA4 Origem da Campanha → {fonte: {métrica: valor}}."""
    rows = read_csv_file(filepath)
    if not rows:
        return {}

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    metric_aliases = {
        "usuarios_ativos": ["usuários ativos", "usuarios ativos", "active users", "total de usuários"],
        "sessoes":          ["sessões", "sessoes", "sessions"],
        "sessoes_eng":      ["sessões engajadas", "sessoes engajadas", "engaged sessions"],
        "tempo_sessao":     ["tempo médio de engajamento por sess",
                             "tempo medio de engajamento por sess",
                             "average engagement time per session"],
        "sessoes_eng_user": ["sessões engajadas por usuário", "sessoes engajadas por usuario",
                             "engaged sessions per"],
        "ev_sessao":        ["eventos por sessão", "eventos por sessao", "events per session"],
        "tx_eng":           ["taxa de engajamento", "engagement rate"],
        "ev_principais":    ["eventos principais", "key events"],
        "contagem_eventos": ["contagem de eventos", "event count"],
        "receita":          ["receita total", "total revenue", "receita"],
    }

    col_map = {}
    for mk, aliases in metric_aliases.items():
        idx = find_col(hdrs, aliases)
        if idx >= 0:
            col_map[mk] = idx

    result = {}
    for row in rows[1:]:
        if not row:
            continue
        src = row[0].replace('"', '').strip()
        if not src or src.lower() in ("total", "totais"):
            continue

        src_data = {}
        for mk, ci in col_map.items():
            v = parse_num(row[ci]) if ci < len(row) else None
            if v is not None:
                src_data[mk] = v

        if src_data:
            result[src] = src_data

    return result


def parse_gsc_grafico(filepath):
    """Search Console Gráfico (diário) → totais mensais para a seção gsc."""
    rows = read_csv_file(filepath)
    if not rows:
        return None

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    cli_idx = find_col(hdrs, ["clique", "click"])
    imp_idx = find_col(hdrs, ["impress"])
    pos_idx = find_col(hdrs, ["posição", "posicao", "position"])

    if cli_idx < 0 or imp_idx < 0:
        return None

    total_cli = total_imp = 0
    wp_pos = []

    for row in rows[1:]:
        if not row:
            continue
        cli = int(parse_num(row[cli_idx] if cli_idx < len(row) else None) or 0)
        imp = int(parse_num(row[imp_idx] if imp_idx < len(row) else None) or 0)
        pos = parse_num(row[pos_idx] if 0 <= pos_idx < len(row) else None)

        total_cli += cli
        total_imp += imp
        if pos is not None and imp > 0:
            wp_pos.append((pos, imp))

    if total_imp == 0 and total_cli == 0:
        return None

    return {
        "cliques":    total_cli,
        "impressoes": total_imp,
        "ctr":        total_cli / total_imp if total_imp else 0,
        "posicao":    weighted_avg(wp_pos),
    }


def parse_gsc_segmento(filepath):
    """Search Console Dispositivos/Países/Aspecto → (tipo, [{n,c,i,p}])."""
    rows = read_csv_file(filepath)
    if not rows:
        return None, None

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    cli_idx = find_col(hdrs, ["clique", "click"])
    imp_idx = find_col(hdrs, ["impress"])
    pos_idx = find_col(hdrs, ["posição", "posicao", "position"])

    if cli_idx < 0 or imp_idx < 0:
        return None, None

    # Detecta tipo pela primeira coluna
    dim_lbl = hdrs[0] if hdrs else ""
    if any(k in dim_lbl for k in ["dispositiv", "device"]):
        dim_type = "device"
    elif any(k in dim_lbl for k in ["pa", "country"]):
        dim_type = "country"
    elif any(k in dim_lbl for k in ["aspecto", "appearance", "snippet"]):
        dim_type = "appearance"
    else:
        dim_type = "other"

    result = []
    for row in rows[1:]:
        if not row:
            continue
        name = row[0].replace('"', '').strip()
        if not name:
            continue
        cli = int(parse_num(row[cli_idx] if cli_idx < len(row) else None) or 0)
        imp = int(parse_num(row[imp_idx] if imp_idx < len(row) else None) or 0)
        pos = parse_num(row[pos_idx] if 0 <= pos_idx < len(row) else None)

        if cli == 0 and imp == 0:
            continue
        result.append({"n": name, "c": cli, "i": imp, "p": pos})

    result.sort(key=lambda x: x["c"], reverse=True)
    return dim_type, result


def parse_gsc_consultas(filepath):
    """Search Console Consultas/Páginas → [{q,c,i,p}] (máx 500)."""
    rows = read_csv_file(filepath)
    if not rows:
        return []

    hdrs = [h.lower().replace('"', '').strip() for h in rows[0]]

    q_idx = find_col(hdrs, ["consulta", "query", "palavra", "keyword"])
    if q_idx < 0:
        q_idx = find_col(hdrs, ["página principal", "páginas principais", "página", "pagina", "page"])
    if q_idx < 0:
        q_idx = 0

    cli_idx = find_col(hdrs, ["clique", "click"])
    imp_idx = find_col(hdrs, ["impress"])
    pos_idx = find_col(hdrs, ["posição", "posicao", "position"])

    if cli_idx < 0 or imp_idx < 0:
        return []

    result = []
    for row in rows[1:]:
        if not row:
            continue
        q = row[q_idx].replace('"', '').strip() if q_idx < len(row) else ""
        if not q:
            continue
        cli = int(parse_num(row[cli_idx] if cli_idx < len(row) else None) or 0)
        imp = int(parse_num(row[imp_idx] if imp_idx < len(row) else None) or 0)
        pos = parse_num(row[pos_idx] if 0 <= pos_idx < len(row) else None)

        if cli == 0 and imp == 0:
            continue
        result.append({"q": q, "c": cli, "i": imp, "p": pos})

    result.sort(key=lambda x: x["i"], reverse=True)
    return result[:500]


# ══════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def process_month(site_dir_name, year_str, month_name, ac, prop, mo_idx, cal_idx):
    month_dir = BASE_DIR / site_dir_name / year_str / month_name
    changes = []

    if not isinstance(ac.get("an"), dict):
        ac["an"] = {}
    an = ac["an"]

    for k in ("data", "campsrc", "seo", "seoseg"):
        an.setdefault(k, {})

    # ── 1. TOP PÁGINAS ────────────────────────────────────────
    f = latest_csv(month_dir / "analytics" / "top páginas")
    if f:
        print(f"    📄 top páginas: {f.name}")
        pages = parse_top_pages(f)
        if pages:
            key = f"{mo_idx}-u-{prop}"
            existing = {item["n"]: item for item in ac.get(key, [])}
            for item in pages:
                if item["n"] in existing:
                    item["prev"] = existing[item["n"]].get("prev", 0)
            ac[key] = pages
            changes.append(f"Top páginas ({len(pages)} URLs)")

    # ── 2. TRÁFEGO ────────────────────────────────────────────
    f = latest_csv(month_dir / "analytics" / "tráfego")
    if f:
        print(f"    📄 tráfego: {f.name}")
        res = parse_trafego(f)
        if res:
            d = ensure_an_data(an, year_str, "traf", prop)
            for mk, val in res["traf"].items():
                if val is not None:
                    d[mk][cal_idx] = val
            if not isinstance(ac.get("hist"), dict):
                ac["hist"] = {}
            ac["hist"].setdefault(year_str, {})
            hist_aquis = ac["hist"][year_str].setdefault("aquis", {})
            for chan_key, sess in res["aquis"].items():
                if not isinstance(hist_aquis.get(chan_key), list):
                    hist_aquis[chan_key] = arr12()
                hist_aquis[chan_key][cal_idx] = sess
            tot = res["traf"].get("sessoes_tot", 0) or 0
            changes.append(f"Tráfego ({int(tot):,} sessões)")

    # ── 3. USUÁRIOS ───────────────────────────────────────────
    f = latest_csv(month_dir / "analytics" / "usuários")
    if f:
        print(f"    📄 usuários: {f.name}")
        res = parse_usuarios(f)
        if res:
            d = ensure_an_data(an, year_str, "user", prop)
            for mk, val in res.items():
                if val is not None and mk in d:
                    d[mk][cal_idx] = val
            tot = res.get("usuarios_tot") or 0
            changes.append(f"Usuários ({int(tot):,} usuários)")

    # ── 4. ORIGEM DE CAMPANHA ─────────────────────────────────
    f = latest_csv(month_dir / "analytics" / "origem de campanha")
    if f:
        print(f"    📄 origem de campanha: {f.name}")
        res = parse_campanha(f)
        if res:
            an["campsrc"].setdefault(year_str, {}).setdefault(prop, {})
            camp = an["campsrc"][year_str][prop]
            for src_name, src_data in res.items():
                camp.setdefault(src_name, {})
                for mk, val in src_data.items():
                    if not isinstance(camp[src_name].get(mk), list):
                        camp[src_name][mk] = arr12()
                    camp[src_name][mk][cal_idx] = val
            changes.append(f"Campanha ({len(res)} origens)")

    # ── 5. SEARCH CONSOLE — GRÁFICO ──────────────────────────
    f = latest_csv(month_dir / "search_console" / "gráfico")
    if f:
        print(f"    📄 SC gráfico: {f.name}")
        res = parse_gsc_grafico(f)
        if res:
            d = ensure_an_data(an, year_str, "gsc", prop)
            for mk, val in res.items():
                if val is not None:
                    d[mk][cal_idx] = val
            changes.append(
                f"GSC gráfico ({res.get('cliques', 0):,} cliques, "
                f"{res.get('impressoes', 0):,} impressões)"
            )

    # ── 6. SEARCH CONSOLE — OPORTUNIDADES ────────────────────
    opp_dir = month_dir / "search_console" / "oportunidades"
    consultas_f = latest_csv_named(opp_dir, "Consultas.csv")
    if consultas_f:
        print(f"    📄 SC consultas: {consultas_f.name}")
        res = parse_gsc_consultas(consultas_f)
        if res:
            an["seo"].setdefault(year_str, {}).setdefault(prop, {})
            an["seo"][year_str][prop][str(cal_idx)] = res
            changes.append(f"SEO Consultas ({len(res)} queries)")

    paginas_f = latest_csv_named(opp_dir, "Páginas.csv")
    if paginas_f:
        print(f"    📄 SC páginas: {paginas_f.name}")
        res = parse_gsc_consultas(paginas_f)
        if res:
            an["seo"].setdefault(year_str, {}).setdefault(prop + "_pages", {})
            an["seo"][year_str][prop + "_pages"][str(cal_idx)] = res
            changes.append(f"SEO Páginas ({len(res)} páginas)")

    # ── 7. SEARCH CONSOLE — SEGMENTOS ────────────────────────
    seg_files = latest_csv_multi(month_dir / "search_console" / "segmentos")
    if seg_files:
        an["seoseg"].setdefault(year_str, {}).setdefault(prop, {})
        seoseg = an["seoseg"][year_str][prop]
        for f in seg_files:
            print(f"    📄 SC segmento: {f.name}")
            dim_type, res = parse_gsc_segmento(f)
            if dim_type and res:
                seoseg.setdefault(dim_type, {})
                seoseg[dim_type][str(cal_idx)] = res
                changes.append(f"SC {dim_type} ({len(res)} linhas)")

    return changes


# ══════════════════════════════════════════════════════════════
# EXECUÇÃO
# ══════════════════════════════════════════════════════════════

def run():
    print("=" * 62)
    print("  🤖  Automação Dashboard — Guardar Dinheiro")
    print(f"  📁  {BASE_DIR}")
    print("=" * 62)

    if not BASE_DIR.exists():
        print(f"\n❌ Pasta não encontrada: {BASE_DIR}")
        return

    print("\n⬇️  Carregando estado atual do Supabase...")
    try:
        state = sb_get("gd_v4")
    except Exception as e:
        print(f"❌ Erro ao conectar ao Supabase: {e}")
        return

    if state is None:
        print("  ℹ️  Nenhum estado encontrado — iniciando do zero.")
        state = {"t": {}, "a": {}, "e": {}}

    for k in ("t", "a", "e"):
        if not isinstance(state.get(k), dict):
            state[k] = {}

    ac = state["a"]
    all_changes = []

    # Escaneia estrutura de pastas
    for site_dir in sorted(BASE_DIR.iterdir()):
        if not site_dir.is_dir():
            continue
        prop = SITE_MAP.get(site_dir.name.lower())
        if not prop:
            print(f"\n⚠️  Site não mapeado (ignorado): {site_dir.name}")
            continue

        for year_dir in sorted(site_dir.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            year_str = year_dir.name

            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                month_name = month_dir.name.lower().strip()
                # Aceita variações (junho, Junho, 06, etc.)
                month_info = MONTH_MAP.get(month_name)
                if not month_info:
                    print(f"\n⚠️  Mês não reconhecido (ignorado): {month_dir.name}")
                    continue

                mo_idx  = month_info["mo_idx"]
                cal_idx = month_info["cal_idx"]

                if mo_idx is None:
                    # Meses fora do array MO não usam top páginas key
                    mo_idx = cal_idx  # fallback

                label = f"{site_dir.name} / {year_str} / {month_dir.name}"
                print(f"\n📅  {label}")

                changes = process_month(
                    site_dir.name, year_str, month_dir.name,
                    ac, prop, mo_idx, cal_idx
                )

                for c in changes:
                    print(f"    ✅ {c}")
                all_changes.extend(changes)

    if not all_changes:
        print("\n⚠️  Nenhum dado processado.")
        print("    Verifique se os CSVs estão nas subpastas corretas.")
        return

    print(f"\n⬆️  Enviando {len(all_changes)} atualização(ões) para o Supabase...")
    try:
        sb_set("gd_v4", {"t": state["t"], "a": ac, "e": state["e"]})
        print("✅  Dashboard atualizado com sucesso!\n")
        print("Resumo:")
        for c in all_changes:
            print(f"  • {c}")
    except Exception as e:
        print(f"❌ Erro ao salvar no Supabase: {e}")


if __name__ == "__main__":
    run()
