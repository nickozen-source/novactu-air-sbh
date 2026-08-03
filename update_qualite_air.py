#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOVACTU SBH — Qualité de l'air — Mise à jour automatique
Page standalone, dédiée uniquement à l'indice de qualité de l'air.
Conçu pour tourner via GitHub Actions (cron) puis déploiement Netlify.

Source : Open-Meteo Air Quality API (modèle CAMS/satellite, coordonnées exactes
de Saint-Barthélemy), gratuite et sans clé. Fournit directement l'indice
officiel "US AQI" — la même méthodologie que l'IQA⁺ US affiché par IQAir,
et bien plus proche de leur valeur qu'une recherche de "station la plus
proche" (souvent à des dizaines/centaines de km sur d'autres îles).
"""

import os, re, json, datetime, urllib.request

TARGET_FILE = "sbh-qualite-air.html"
LAT, LON = 17.9, -62.83  # Saint-Barthélemy

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

def http_get(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NovactuSBH-Air/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        log(f"  ⚠ {url[:70]} → {e}")
        return ""

POLLUANT_FR = {
    "us_aqi_pm2_5": "PM2.5 · particules fines",
    "us_aqi_pm10":  "PM10 · particules grossières",
    "us_aqi_ozone": "Ozone (O₃)",
    "us_aqi_no2":   "Dioxyde d'azote (NO₂)",
    "us_aqi_so2":   "Dioxyde de soufre (SO₂)",
    "us_aqi_co":    "Monoxyde de carbone (CO)",
}

def classify_aqius(aqi):
    """Renvoie (classe_css, libellé) à partir de l'US AQI (échelle officielle, simplifiée en 4 zones)."""
    if aqi <= 50:
        return "bon", "Bon"
    elif aqi <= 100:
        return "moderee", "Modéré"
    elif aqi <= 150:
        return "mauvais", "Mauvais"
    else:
        return "tresmauvais", "Très mauvais"

BADGES = {
    "bon":         ("✓ Air sain aujourd'hui",
                     "Pas de restriction. Idéal pour le sport et la plage."),
    "moderee":     ("⚠ Qualité modérée",
                     "Personnes sensibles : limitez les efforts prolongés en extérieur."),
    "mauvais":     ("⚠ Air dégradé pour les personnes sensibles",
                     "Réduisez les activités physiques intenses en extérieur, surtout enfants, seniors et asthmatiques."),
    "tresmauvais": ("⛔ Air très dégradé",
                     "Évitez les efforts prolongés en extérieur. Restez à l'intérieur si possible."),
}

SEVERITY = {"bon": 0, "moderee": 1, "mauvais": 2, "tresmauvais": 3}
BRUME_TEXT = {
    "bon":         ("Aucun épisode détecté",
                     "Air pur sur les Îles du Nord. Visibilité excellente.<br>Activités extérieures libres pour tous."),
    "moderee":     ("Épisode modéré détecté",
                     "Présence de brume saharienne. Personnes sensibles : limitez l'exposition prolongée."),
    "mauvais":     ("Épisode marqué détecté",
                     "Brume saharienne bien visible sur les images satellite. Réduisez les efforts prolongés en extérieur."),
    "tresmauvais": ("Épisode intense détecté",
                     "Brume saharienne marquée. Évitez les efforts prolongés en extérieur, surtout personnes sensibles."),
}

def scale_marker_pct(aqi):
    """Position (%) du curseur sur l'échelle visuelle à 4 zones égales (0-25-50-75-100), seuils US AQI 50/100/150."""
    if aqi <= 50:
        pct = (aqi / 50) * 25
    elif aqi <= 100:
        pct = 25 + ((aqi - 50) / 50) * 25
    elif aqi <= 150:
        pct = 50 + ((aqi - 100) / 50) * 25
    else:
        pct = 75 + min(1, (aqi - 150) / 150) * 25
    return round(max(0, min(100, pct)), 1)

def fetch_air():
    """Source unique : Open-Meteo Air Quality API — indice US AQI officiel calculé
    par modèle (CAMS) aux coordonnées exactes de Saint-Barth, comme IQAir."""
    log("🌿 Qualité air (Open-Meteo, modèle CAMS)...")
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=us_aqi,us_aqi_pm2_5,us_aqi_pm10,us_aqi_ozone,us_aqi_no2,us_aqi_so2,us_aqi_co,dust"
        "&timezone=America%2FSt_Barthelemy&forecast_days=1"
    )
    raw = http_get(url)
    if not raw:
        return None
    try:
        d = json.loads(raw)
        h = d.get("hourly", {})
        aqi = round(h.get("us_aqi", [50])[0] or 50)
        dust = round(h.get("dust", [0])[0] or 0, 1)

        subs = {}
        for key in ("us_aqi_pm2_5", "us_aqi_pm10", "us_aqi_ozone", "us_aqi_no2", "us_aqi_so2", "us_aqi_co"):
            val = h.get(key, [None])[0]
            if val is not None:
                subs[key] = val
        main_code = max(subs, key=subs.get) if subs else "us_aqi_pm2_5"
        main_label = POLLUANT_FR.get(main_code, "PM2.5 · particules fines")

        lvl_class, lvl_label = classify_aqius(aqi)
        badge_title, badge_desc = BADGES[lvl_class]
        pct = scale_marker_pct(aqi)

        # Brume saharienne : proxy dust d'open-meteo, plafonné par le niveau IQA
        # (à Saint-Barth une dégradation de l'air vient quasi toujours du sable saharien)
        dust_class = "bon"
        if dust > 40:
            dust_class = "tresmauvais"
        elif dust > 15:
            dust_class = "moderee"
        if SEVERITY.get(lvl_class, 0) > SEVERITY.get(dust_class, 0):
            dust_class = lvl_class
        brume, brume_desc = BRUME_TEXT[dust_class]

        result = {
            "iqa": aqi, "lvl_class": lvl_class, "lvl_label": lvl_label,
            "main_label": main_label, "pct": pct,
            "badge_title": badge_title, "badge_desc": badge_desc,
            "dust_class": dust_class, "brume": brume, "brume_desc": brume_desc,
        }
        log(f"  ✓ US AQI {aqi} ({lvl_label}) · polluant principal {main_label} · dust {dust} → {brume}")
        return result
    except Exception as e:
        log(f"  ✗ {e}")
        return None

def get_date_str():
    tz  = datetime.timezone(datetime.timedelta(hours=-4))
    now = datetime.datetime.now(tz)
    mois = ["","janvier","février","mars","avril","mai","juin",
            "juillet","août","septembre","octobre","novembre","décembre"]
    return f"{now.day} {mois[now.month]} {now.year}"

DUST_DOT_COLORS = {
    "bon":         ("#6fcf97", "rgba(111,207,151,0.5)"),
    "moderee":     ("#f2c94c", "rgba(242,201,76,0.5)"),
    "mauvais":     ("#f2994a", "rgba(242,153,74,0.5)"),
    "tresmauvais": ("#eb5757", "rgba(235,87,87,0.5)"),
}

def patch(html, air, date_str):
    if not air:
        return html
    a = air

    html = re.sub(r'(<div id="air-date">)[^<]*(</div>)',
                  rf'\g<1>{date_str}\g<2>', html)

    html = re.sub(
        r'(<div class="iqa-circle )[^"]*(" id="iqa-circle">)',
        rf'\g<1>bg-{a["lvl_class"]} lvl-{a["lvl_class"]}\g<2>', html
    )
    html = re.sub(r'(<span class="iqa-num" id="iqa-num">)\d+(</span>)',
                  rf'\g<1>{a["iqa"]}\g<2>', html)

    html = re.sub(
        r'(<div class="iqa-label" id="iqa-label">)[^<]*(</div>)',
        rf'\g<1>{a["lvl_label"]}\g<2>', html
    )

    html = re.sub(
        r'(<div class="iqa-src">)[^<]*(</div>)',
        rf'\g<1>Source · modèle CAMS (Open-Meteo) · polluant principal : {a["main_label"]}\g<2>', html
    )

    html = re.sub(
        r'(<div class="iqa-scale-marker" id="iqa-scale-marker" style="left:)[\d.]+%(;"></div>)',
        rf'\g<1>{a["pct"]}%\g<2>', html
    )

    dot_color, dot_glow = DUST_DOT_COLORS[a["dust_class"]]
    html = re.sub(
        r'(<div class="air-brume-dot )[^"]*(" id="brume-dot" style=")[^"]*(">)',
        rf'\g<1>lvl-{a["dust_class"]}\g<2>background:{dot_color};box-shadow:0 0 8px {dot_glow};\g<3>', html
    )
    html = re.sub(
        r'(<span class="air-brume-status )[^"]*(" id="brume-status">)[^<]*(</span>)',
        rf'\g<1>lvl-{a["dust_class"]}\g<2>{a["brume"]}\g<3>', html
    )
    html = re.sub(
        r'(<div class="air-brume-desc" id="brume-desc">).*?(</div>)',
        rf'\g<1>{a["brume_desc"]}\g<2>', html, flags=re.DOTALL
    )

    html = re.sub(
        r'(<div class="air-badge )[^"]*(" id="air-badge">)',
        rf'\g<1>badge-{a["lvl_class"]}\g<2>', html
    )
    html = re.sub(
        r'(<div class="air-badge-title )[^"]*(" id="air-badge-title">)[^<]*(</div>)',
        rf'\g<1>lvl-{a["lvl_class"]}\g<2>{a["badge_title"]}\g<3>', html
    )
    html = re.sub(
        r'(<div class="air-badge-desc" id="air-badge-desc">)[^<]*(</div>)',
        rf'\g<1>{a["badge_desc"]}\g<2>', html
    )

    return html

def main():
    log("=" * 52)
    log("NOVACTU SBH — Qualité de l'air — Mise à jour")
    log("=" * 52)

    if not os.path.exists(TARGET_FILE):
        log(f"✗ {TARGET_FILE} introuvable dans le repo")
        return

    air = fetch_air()
    if not air:
        log("✗ Échec de récupération — fichier inchangé")
        return

    date_str = get_date_str()

    log("✏️  Mise à jour du fichier...")
    with open(TARGET_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    html = patch(html, air, date_str)
    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    log("=" * 52)
    log("✅ Terminé — GitHub Actions va déployer sur Netlify")
    log("=" * 52)

if __name__ == "__main__":
    main()
