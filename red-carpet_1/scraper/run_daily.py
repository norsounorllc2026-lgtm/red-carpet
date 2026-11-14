#!/usr/bin/env python3
# =============================================================================
#  RED CARPET DAILY — Black American fashion designers, barbers & hair
#  stylists, and makeup artists news finder
# =============================================================================
#
#  WHAT THIS SCRIPT DOES (once per day, run automatically by GitHub Actions)
#  -------------------------------------------------------------------------
#  It does the steps below THREE times, once for each gallery on the page:
#     - Fashion Designers ........ 10-slot carousel + category drop-downs
#     - Barbers & Hair Stylists .. 4-slot gallery
#     - Makeup Artists ........... 4-slot gallery
#  Each gallery has its own list, its own Rolodex position and its own topic
#  words for the backup check (fashion / hair / makeup). The memory of what
#  was already posted is shared, so no article is ever posted twice.
#
#  1. Opens its "memory" file (data/state.json):
#       - where it stopped in the designer list yesterday ("the Rolodex"),
#       - which articles it has already posted (so it never posts them twice),
#       - what is currently sitting in every carousel / category slot.
#  2. Starting with the NEXT designer after yesterday's stopping point, it goes
#     straight down the list and searches news feeds for anything posted about
#     that designer in roughly the last day.
#       - Nothing found ............................ skip to next designer
#       - Same article, same source as before ...... skip to next designer
#       - New article (or same story, new source) .. POST IT
#  2b. BACKUP CHECK — before anything is posted it must pass every check:
#       - the article link opens (a real page, not an error or dead link)
#       - the article is in English
#       - the ARTICLE ITSELF names the designer/brand (not just the search
#         preview), with fashion words right next to the name (stops wrong
#         people with the same name, and names that are everyday words)
#       - the best photo is chosen: photos the article captions with the
#         designer's name come first; logos, icons, tiny pictures, banner
#         strips, broken images, the publisher's generic share picture and
#         photos already showing in the carousel are all rejected
#       - the designer's website link opens (otherwise a search link is used)
#     If an article fails, the next article for that designer is tried; if
#     none pass, the script moves on to the next designer. Every pass/fail
#     and the reason is written to data/checks.json so you can review it.
#  3. Each new post goes into the next carousel slot (slot 1, then 2 ... 10)
#     and into the next open slot of every category that designer belongs to
#     (up to 5 per category).
#  4. When every slot has been refreshed for the day, it STOPS and remembers
#     which designer is next. If it reaches the bottom of the list it wraps to
#     the top once, then stops (so it can never loop forever).
#  5. Slots that did not get a new post today KEEP yesterday's post — nothing
#     is ever left empty. On the very first run, any slot still empty is filled
#     with a "profile" card for a designer (their website image, or a gold
#     monogram if no image can be found).
#  6. Writes three files:
#       - data/feed.json   -> what your Wix page reads and displays
#       - data/state.json  -> the script's memory for tomorrow
#       - data/checks.json -> today's backup-check report (what passed,
#                             what was rejected and why)
#
#  NOTHING ELSE IS STORED. No database, no Wix CMS. The designer list lives
#  right here in this file (Section 2).
#
#  HOW TO RUN BY HAND (optional — GitHub runs it for you every day)
#       pip install -r scraper/requirements.txt
#       python scraper/run_daily.py            # real run
#       python scraper/run_daily.py --test     # offline practice run, fake news
#
#  TABLE OF CONTENTS
#     Section 1  Settings you can change
#     Section 2  The designer list (edit names, websites, categories here)
#     Section 3  Category buttons (labels shown on the website)
#     Section 3b Barbers & hair stylists list, makeup artists list
#     Section 3c The three galleries (slots and topic words for each)
#     Section 3d Where each person is from (shown on their card)
#     Section 4  Small helper tools
#     Section 5  Searching the news feeds
#     Section 6  Backup check: article, photo and website verification
#     Section 7  The memory file (load / save)
#     Section 8  The daily Rolodex run (the main logic)
#     Section 9  First-run fallback: fill empty slots with profile cards
#     Section 10 Writing the files the website reads
#     Section 11 Offline test mode
#     Section 12 Start button
# =============================================================================

import json
import os
import re
import sys
import time
import html
import random
import datetime as dt
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import xml.etree.ElementTree as ET


# =============================================================================
#  SECTION 1 — SETTINGS YOU CAN CHANGE
# =============================================================================

CAROUSEL_SLOTS = 10            # how many pictures the top carousel holds
GALLERY_SLOTS = 4              # how many professionals each of the two new
                               # galleries holds (Barbers & Hair, Makeup)
CATEGORY_SLOTS = 5             # how many designers show in each drop-down
LOOKBACK_HOURS = 36            # how far back counts as "today's" news
                               # (36h covers time-zone gaps and late postings)
REMEMBER_POSTED_DAYS = 90      # how long to remember an article so it is
                               # never posted twice (older memory is cleared)
PAUSE_BETWEEN_SEARCHES = 2.0   # seconds to wait between designers, so the
                               # news sites are not flooded with requests
REQUEST_TIMEOUT = 12           # seconds to wait for any single web page

# ---- "Get details" link on every card ----
# This is the ORIGINAL search link the cards used: it opens a search for the
# person, where the search engine's AI answer shows their details, website and
# contact info. Bing is what the cards first used. To use Google instead,
# change it to "https://www.google.com/search?q=".
DETAILS_SEARCH = "https://www.bing.com/search?q="
PHOTO_REFRESH_DAYS = 30        # how often a person's found photo is looked up again

# ---- Backup check settings ----
MIN_PHOTO_SIDE = 400           # photos smaller than this (pixels) are rejected
MAX_PHOTO_RATIO = 2.6          # wider/taller than 2.6:1 = banner strip, rejected
MAX_ARTICLES_PER_DESIGNER = 4  # how many of a designer's new articles to try
                               # before giving up and moving to the next one
# Words that prove an article is about fashion (at least FASHION_WORDS_NEEDED
# different ones must appear in the article text)
FASHION_WORDS = ["fashion", "designer", "design", "collection", "runway", "couture",
                 "brand", "apparel", "clothing", "style", "wear", "dress", "denim",
                 "handbag", "jewelry", "sneaker", "label", "fashion week", "boutique",
                 "garment", "menswear", "womenswear", "streetwear", "outfit", "capsule"]
# The same check for the two new galleries uses their own words:
HAIR_WORDS = ["hair", "hairstyle", "hairstylist", "hair stylist", "stylist", "barber",
              "barbershop", "haircut", "fade", "braids", "braided", "locs", "wig",
              "salon", "curls", "natural hair", "updo", "blowout", "silk press",
              "ponytail", "edges", "lace front", "taper", "lineup", "hair care", "glam"]
MAKEUP_WORDS = ["makeup", "make-up", "makeup artist", "beauty", "glam", "lipstick",
                "lip liner", "lip gloss", "foundation", "concealer", "cosmetics",
                "eyeshadow", "eyeliner", "mascara", "blush", "bronzer", "brow", "lash",
                "complexion", "contour", "highlighter", "palette", "skincare", "mua"]
FASHION_WORDS_NEEDED = 2
NEAR_NAME_CHARACTERS = 400     # how close (in characters) those fashion words
                               # must be to the designer's name or brand
# Words in a picture's address that mean it is NOT a photo of the designer/work
BAD_PHOTO_WORDS = ["logo", "icon", "favicon", "sprite", "placeholder", "default",
                   "avatar", "blank", "spacer", "pixel", "badge", "button", "banner-ad",
                   "share-image", "social-share", "og-default", "fallback", "1x1"]

# Where the files are written (relative to the project folder)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED_FILE = os.path.join(PROJECT_DIR, "data", "feed.json")
STATE_FILE = os.path.join(PROJECT_DIR, "data", "state.json")
CHECKS_FILE = os.path.join(PROJECT_DIR, "data", "checks.json")

# A normal browser identity, so news sites send regular pages back
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 RedCarpetDaily/1.0")


# =============================================================================
#  SECTION 2 — THE DESIGNER LIST
# =============================================================================
#  The script walks this list from top to bottom, like a Rolodex.
#
#  Each designer has:
#    name   -> shown on the website
#    brand  -> shown on the website
#    cats   -> which category buttons they appear under (keys from Section 3)
#    site   -> their website ("" if unknown; the page then links to a search).
#              PLEASE CHECK THESE — any wrong link is easy to fix here.
#    query  -> what is typed into the news search
#    match  -> at least ONE of these words must appear in the article, or it
#              is ignored. Use full names or full brand names only — never a
#              word that is also an everyday first name or word (for example
#              "Aliette" is a common French first name, so Jason Rembert's
#              entry matches only "Jason Rembert").
#    require-> (optional) the article must ALSO contain one of these, for
#              brands whose name has another meaning (e.g. Diotima).
#
#  TO ADD A DESIGNER: copy any line, paste it where you want them in the
#  Rolodex order, and change the details. TO REMOVE: delete the line.
# -----------------------------------------------------------------------------

def D(name, brand, cats, site="", query=None, match=None, require=None):
    """Shortcut that builds one designer entry."""
    return {
        "name": name,
        "brand": brand,
        "cats": cats,
        "site": site,
        "query": query or f'"{name}"',
        "match": match or [name],
        "require": require or [],   # extra words the article must ALSO contain
        "group": "designers",        # which gallery (set automatically)
        "origin": "",                # shown on the card (Section 3d)
    }

DESIGNERS = [
    # ---- Your original starter list -----------------------------------------
    D("Christopher John Rogers", "Christopher John Rogers", ["dresses", "couture"], "https://www.christopherjohnrogers.com"),
    D("LaQuan Smith", "LaQuan Smith", ["dresses"], "https://www.laquansmith.com"),
    D("Sergio Hudson", "Sergio Hudson", ["suiting", "dresses"], "https://www.sergiohudson.com"),
    D("Telfar Clemens", "Telfar", ["bags", "streetwear"], "https://telfar.net",
      query='"Telfar"', match=["Telfar"]),
    D("Brandon Blackwood", "Brandon Blackwood New York", ["bags"], "https://brandonblackwood.com"),
    D("Victor Glemaud", "Victor Glemaud", ["knitwear"], "https://www.victorglemaud.com"),
    D("Frederick Anderson", "Frederick Anderson", ["knitwear", "suiting"], "https://www.frederickandersondesigner.com",
      query='"Frederick Anderson" fashion'),
    D("Kimberly Goldson", "Kimberly Goldson", ["suiting", "dresses"], "https://kimberlygoldson.com"),
    D("Jerry Lorenzo", "Fear of God", ["streetwear", "comfort"], "https://fearofgod.com",
      query='"Fear of God" OR "Jerry Lorenzo"', match=["Jerry Lorenzo", "Fear of God"]),
    D("Tremaine Emory", "Denim Tears", ["denim", "streetwear"], "https://denimtears.com",
      query='"Denim Tears" OR "Tremaine Emory"', match=["Denim Tears", "Tremaine Emory"]),
    D("Kerby Jean-Raymond", "Pyer Moss", ["suiting", "couture"], "https://pyermoss.com",
      query='"Pyer Moss" OR "Kerby Jean-Raymond"', match=["Pyer Moss", "Kerby Jean-Raymond"]),
    D("Heron Preston", "Heron Preston", ["streetwear"], "https://www.heronpreston.com"),
    D("Dapper Dan", "Dapper Dan of Harlem", ["couture", "suiting"], "https://dapperdanofharlem.com",
      query='"Dapper Dan"', match=["Dapper Dan"]),
    D("Pharrell Williams", "Billionaire Boys Club / ICECREAM", ["streetwear"], "https://www.bbcicecream.com",
      query='"Billionaire Boys Club"', match=["Billionaire Boys Club"]),
    D("Don C", "Just Don", ["streetwear", "bags"], "https://justdon.com",
      query='"Just Don" OR "Don C"', match=["Just Don", "Don C"]),
    D("Felisha Noel", "Fe Noel", ["dresses", "swim"], "https://fenoel.com",
      query='"Fe Noel" OR "Felisha Noel"', match=["Fe Noel", "Felisha Noel"]),
    D("Rebecca Henry & Akua Shabaka", "House of Aama", ["dresses"], "https://houseofaama.com",
      query='"House of Aama"', match=["House of Aama"]),
    D("Undra Celeste", "Undra Celeste New York", ["suiting"], "https://www.undracelesteny.com"),
    D("Brittany Kozerski", "Jade Swim", ["swim"], "https://jadeswim.com",
      query='"Jade Swim"', match=["Jade Swim", "Brittany Kozerski"]),
    D("Aaron Potts", "A.Potts", ["comfort", "suiting"], "https://www.apottscollection.com",
      query='"Aaron Potts" OR "A.Potts"', match=["Aaron Potts", "A.Potts", "APOTTS"]),
    D("Connor McKnight", "Connor McKnight", ["suiting"], "https://connormcknight.com"),
    D("Keith Herron", "Advisry", ["streetwear"], "https://advisry.shop",
      query='"Advisry"', match=["Advisry", "Keith Herron"]),
    D("Pierre Davis, Arin Hayes & Autumn Randolph", "No Sesso", ["dresses", "streetwear"], "https://nosesso.com",
      query='"No Sesso"', match=["No Sesso"]),
    D("Sebastien Amisial", "Sebastien Ami", ["suiting", "knitwear"], "https://www.sebastienami.com",
      query='"Sebastien Ami"', match=["Sebastien Ami"]),
    D("Letesha Renee", "Eugene Taylor", ["knitwear", "comfort"], "https://blackownedeverything.co/collections/eugene-taylor-brand",
      query='"Eugene Taylor" OR "Letesha Renee"', match=["Letesha Renee", "Eugene Taylor"]),
    D("Romeo Hunte", "Romeo Hunte", ["denim", "streetwear"], "https://romeohunte.com"),
    D("Ev Bravado & Téla D'Amore", "Who Decides War", ["denim", "streetwear"], "https://whodecideswar.com",
      query='"Who Decides War"', match=["Who Decides War"]),
    D("Charles Harbison", "Harbison Studio", ["dresses", "suiting"], "https://harbison.studio",
      query='"Charles Harbison" OR "Harbison Studio"', match=["Charles Harbison", "Harbison Studio"]),

    # ---- New York ------------------------------------------------------------
    D("Edvin Thompson", "Theophilio", ["dresses", "streetwear"], "https://theophilio.com",
      query='"Theophilio"', match=["Theophilio", "Edvin Thompson"]),
    D("Rachel Scott", "Diotima", ["knitwear", "dresses"], "",
      query='"Diotima" "Rachel Scott"', match=["Diotima"], require=["Rachel Scott"]),
    D("Shayne Oliver", "Hood By Air", ["streetwear"], "https://hoodbyair.com",
      query='"Hood By Air" OR "Shayne Oliver"', match=["Hood By Air", "Shayne Oliver"]),
    D("Maxwell Osborne", "Public School NY", ["suiting", "streetwear"], "https://www.publicschoolnyc.com",
      query='"Maxwell Osborne"', match=["Maxwell Osborne"]),
    D("Byron Lars", "In Earnest by Byron Lars", ["dresses"], "https://inearnestofficial.com"),
    D("Stephen Burrows", "Stephen Burrows", ["dresses", "couture"], "https://stephenburrows.com"),
    D("B Michael", "B Michael America", ["couture", "dresses"], "https://bmichaelamerica.com",
      query='"B Michael" designer', match=["B Michael"]),
    D("Jason Rembert", "Aliétte", ["dresses"], "",
      query='"Jason Rembert"', match=["Jason Rembert"]),
    D("Brick Owens & Dieter Grams", "Bstroy", ["streetwear"], "https://bstroy.com",
      query='"Bstroy"', match=["Bstroy", "BSTROY", "B.Stroy"]),
    D("Jerome LaMaar", "5:31 Jérôme", ["dresses"], "http://www.jeromelamaarrice.com",
      query='"Jerome LaMaar"', match=["Jerome LaMaar", "Jérôme LaMaar"]),
    D("April Walker", "Walker Wear", ["streetwear", "denim"], "https://walkerwear.com",
      query='"April Walker" OR "Walker Wear"', match=["April Walker", "Walker Wear"]),
    D("Daymond John, J. Alexander Martin, Keith Perrin & Carl Brown", "FUBU", ["streetwear", "denim"], "https://fubu.com",
      query='"FUBU"', match=["FUBU"]),
    D("Kimora Lee Simmons", "Baby Phat", ["streetwear", "denim", "comfort"], "https://babyphat.com",
      query='"Baby Phat"', match=["Baby Phat", "Kimora Lee Simmons"]),
    D("Russell Simmons", "Phat Farm", ["streetwear"], "",
      query='"Phat Farm"', match=["Phat Farm"]),
    D("Shawn Carter (Jay-Z), Damon Dash & Kareem Burke", "Rocawear", ["streetwear", "denim"], "https://rocawear.com",
      query='"Rocawear"', match=["Rocawear"]),
    D("Sean Combs", "Sean John", ["streetwear", "comfort", "denim"], "",
      query='"Sean John" clothing', match=["Sean John"]),
    D("Shiara Robinson", "LaSette", ["swim"], "https://www.lasette.shop",
      query='"LaSette" lingerie', match=["LaSette", "Shiara Robinson"]),
    D("Aisha McShaw", "Aisha McShaw", ["bags"], "https://aishamcshaw.com"),
    D("Matthew Harris", "Mateo New York", ["jewelry"], "https://mateonewyork.com",
      query='"Mateo New York"', match=["Mateo New York"]),
    D("Johnny Nelson", "Johnny Nelson", ["jewelry"], "https://johnnynelson.nyc",
      query='"Johnny Nelson" jewelry', match=["Johnny Nelson"]),
    D("Dynasty & Soull Ogun", "L'enchanteur", ["jewelry"], "https://www.lenchanteur.co",
      query='"L\'enchanteur" jewelry', match=["L'enchanteur", "L’enchanteur"]),
    D("Simone I. Smith", "Simone I. Smith", ["jewelry"], "https://simoneismith.com",
      query='"Simone I. Smith"', match=["Simone I. Smith"]),

    # ---- California ----------------------------------------------------------
    D("Kenneth Nicholson", "Kenneth Nicholson", ["suiting"], "https://www.kennethnicholson.net"),
    D("Kevan Hall", "Kevan Hall Designs", ["dresses", "couture"], "https://kevanhalldesigns.com"),
    D("Carl Jones & TJ Walker", "Cross Colours", ["streetwear", "denim"], "https://crosscolours.com",
      query='"Cross Colours"', match=["Cross Colours"]),
    D("Karl Kani", "Karl Kani", ["denim", "streetwear"], "https://karlkani.com"),
    D("Angela Dean", "Deanzign", ["dresses"], "https://deanzign.net",
      query='"Angela Dean" designer'),
    D("Okera Banks", "Okera Banks", ["dresses"], "https://okerabanks.com"),
    D("BJ Gray", "Grayscale", ["dresses"], "",
      query='"BJ Gray" designer', match=["BJ Gray"]),
    D("James Flemons", "Phlemuns", ["denim", "streetwear"], "",
      query='"Phlemuns"', match=["Phlemuns", "James Flemons"]),
    D("Megan Renee", "Megan Renee", ["dresses"], "https://meganrenee.co",
      query='"Megan Renee" designer'),
    D("Tyler, the Creator", "Golf Wang / Golf le Fleur", ["streetwear"], "https://golfwang.com",
      query='"Golf Wang" OR "Golf le Fleur"', match=["Golf Wang", "Golf le Fleur", "GOLF WANG"]),
    D("Ye (Kanye West)", "Yeezy", ["comfort"], "https://yeezy.com",
      query='"Yeezy" fashion', match=["Yeezy", "YEEZY"]),
    D("Elisa Johnson", "Elisa Johnson", ["jewelry"], "https://elisajohnson.co",
      query='"Elisa Johnson" eyewear OR sunglasses OR fashion'),

    # ---- Illinois ------------------------------------------------------------
    D("Joe Robinson", "Joe Freshgoods", ["streetwear"], "https://joefreshgoods.com",
      query='"Joe Freshgoods"', match=["Joe Freshgoods", "Joe FreshGoods"]),
    D("Sheila Rashid", "Sheila Rashid", ["denim", "comfort"], "https://www.sheilarashid.com"),
    D("Jameel Mohammed", "Khiry", ["jewelry"], "https://khiry.com",
      query='"Jameel Mohammed" OR "Khiry jewelry"', match=["Jameel Mohammed"]),
    D("Stevie Edwards", "I Luv Stevie (legacy)", ["dresses"], "https://www.facebook.com/iluvstevieboutique/",
      query='"Stevie Edwards" designer'),
    D("Andre Walker", "Andre Walker", ["couture"], "",
      query='"Andre Walker" designer'),
    D("Virgil Abloh", "Off-White", ["streetwear", "couture"], "https://www.off---white.com",
      query='"Virgil Abloh"', match=["Virgil Abloh"]),

    # ---- Georgia -------------------------------------------------------------
    D("Keyondra & Kim Lockett", "Jolie Noire", ["comfort"], "https://jolienoire.com",
      query='"Jolie Noire"', match=["Jolie Noire"]),
    D("Quintin Crumpler", "Goat by James King", ["streetwear"], "https://www.goatbyjamesking.com",
      query='"Quintin Crumpler" OR "Goat by James King"', match=["Quintin Crumpler", "Goat by James King"]),
    D("Kenya Freeman", "Sylvia Mollie", ["dresses"], "https://kenyafreeman.com",
      query='"Sylvia Mollie"', match=["Sylvia Mollie"]),
    D("Tracy Nicole", "Tracy Nicole", ["dresses"], "",
      query='"Tracy Nicole" designer'),

    # ---- Texas ---------------------------------------------------------------
    D("Tacharra Perry", "CHAR / CHARWorkroom", ["dresses", "comfort"], "",
      query='"Tacharra Perry" OR "CHARWorkroom"', match=["Tacharra Perry", "CHARWorkroom"]),
    D("Gwendolyn Davis", "Alexandria Lee Designs", ["dresses"], "https://www.facebook.com/p/Alexandria-Lee-Designs-100037660397926/",
      query='"Alexandria Lee Designs"', match=["Alexandria Lee Designs"]),
    D("Isaac Moore", "Isaac & Moore", ["bags"], "https://www.isaacandmoore.com",
      query='"Isaac & Moore" OR "Isaac and Moore"', match=["Isaac & Moore", "Isaac and Moore"]),
    D("Stephanie Evans", "Pamoja Bags", ["bags"], "https://www.pamojabags.com",
      query='"Pamoja Bags"', match=["Pamoja Bags"]),
    D("Kemi Alao", "KYRA", ["dresses"], "https://www.facebook.com/thekyracompany/",
      query='"Kemi Alao"', match=["Kemi Alao"]),
    D("Venny Etienne", "Levenity", ["streetwear"], "https://levenity.com",
      query='"Venny Etienne" OR "Levenity"', match=["Venny Etienne", "Levenity"]),

    # ---- Michigan ------------------------------------------------------------
    D("Tracy Reese", "Hope for Flowers", ["dresses"], "https://hopeforflowers.com",
      query='"Tracy Reese" OR "Hope for Flowers"', match=["Tracy Reese", "Hope for Flowers"]),
    D("Maurice Malone", "Maurice Malone", ["denim"], "https://mauricemaloneusa.com"),
    D("Isaiah Hemmingway", "Isaiah Hemmingway", ["suiting"], "http://www.ihemmingway.com"),
    D("Sharryl Cross", "Truth", ["dresses"], "https://www.truthbebold.shop",
      query='"Sharryl Cross"', match=["Sharryl Cross"]),
    D("Latricesa Myonne", "Latricesa Myonne Fashions", ["dresses"], "https://www.myonnefashion.net"),

    # ---- Maryland / Louisiana ------------------------------------------------
    D("Bishme Cromartie", "Bishme Cromartie", ["dresses", "couture"], "https://bishmecromartie.com"),
    D("Regina Porter", "Gina Gant", ["jewelry"], "https://ginagant.com",
      query='"Gina Gant"', match=["Gina Gant"]),

    # ---- Legacy icons --------------------------------------------------------
    D("Willi Smith", "WilliWear", ["streetwear", "couture"], "",
      query='"Willi Smith" designer', match=["Willi Smith", "WilliWear"]),
    D("Ann Lowe", "Ann Lowe", ["couture", "dresses"], "",
      query='"Ann Lowe" designer'),
    D("Arthur McGee", "Arthur McGee", ["couture"], "",
      query='"Arthur McGee" designer'),
    D("Scott Barrie", "Scott Barrie", ["couture", "dresses"], "",
      query='"Scott Barrie" designer'),
    D("Zelda Wynn Valdes", "Chez Zelda", ["couture"], "",
      query='"Zelda Wynn Valdes"'),
    D("Edward Wilkerson", "Lida Davis", ["couture"], "",
      query='"Edward Wilkerson" designer'),
    D("Jay Jaxon", "Jay Jaxon", ["couture"], ""),
    D("Patrick Kelly", "Patrick Kelly Paris", ["couture", "dresses"], "",
      query='"Patrick Kelly" designer'),
    D("Elizabeth Keckley", "Elizabeth Keckley", ["couture"], ""),

    # ---- Born outside the U.S. (their country is shown on the card) ----------
    D("Anifa Mvuemba", "Hanifa", ["dresses"], "https://hanifa.co",
      query='"Hanifa" fashion OR "Anifa Mvuemba"', match=["Anifa Mvuemba"]),
    D("Esé Azénabor", "Esé Azénabor", ["dresses", "couture"], "https://www.eseazenabor.com",
      query='"Ese Azenabor" OR "Esé Azénabor"', match=["Esé Azénabor", "Ese Azenabor"]),
    D("Omar Salam", "Sukeina", ["dresses", "couture"], "https://www.sukeina.co",
      query='"Sukeina" OR "Omar Salam" fashion', match=["Sukeina", "Omar Salam"]),
    D("Aurora James", "Brother Vellies", ["bags"], "https://brothervellies.com",
      query='"Brother Vellies" OR "Aurora James"', match=["Brother Vellies", "Aurora James"]),
    D("Rihanna", "Savage X Fenty", ["swim"], "https://www.savagex.com",
      query='"Savage X Fenty"', match=["Savage X Fenty", "Savage x Fenty"]),
]


# =============================================================================
#  SECTION 3 — CATEGORY BUTTONS
# =============================================================================
#  The "key" on the left is what you type in a designer's "cats" list above.
#  The label on the right is what visitors see on the button.
#  (The little icon for each button is drawn in the Wix embed file.)
# -----------------------------------------------------------------------------

CATEGORIES = {
    "dresses":    "Dresses & Eveningwear",
    "suiting":    "Suiting & Tailoring",
    "denim":      "Denim",
    "streetwear": "Streetwear",
    "knitwear":   "Knitwear",
    "comfort":    "Comfort Wear & Athleisure",
    "swim":       "Swimwear & Lingerie",
    "bags":       "Handbags & Accessories",
    "jewelry":    "Jewelry & Eyewear",
    "couture":    "Couture & Legacy Icons",
}


# =============================================================================
#  SECTION 3b — BARBERS & HAIR STYLISTS, AND MAKEUP ARTISTS
# =============================================================================
#  These two lists work exactly like the designer list: the same Rolodex, the
#  same backup check, the same memory. Each has its own gallery of
#  GALLERY_SLOTS (4) on the page. "brand" is their business or what they are
#  known for. Leave "site" as "" if unknown — the script looks it up.
#  The words in "query" are what is searched; "match" must be FULL names.
# -----------------------------------------------------------------------------

def P(name, brand, site="", query=None, match=None, require=None):
    """Shortcut for one barber, hair stylist or makeup artist."""
    return D(name, brand, [], site, query, match, require)

HAIR_PROS = [
    # ---- Celebrity hair stylists -----------------------------------------------
    P("Ursula Stephen", "Ursula Stephen The Salon", "https://www.a-frameagency.com/artists/us/hair/ursula-stephen",
      query='"Ursula Stephen" hair'),
    P("Kim Kimble", "Kimble Hair Care", "https://shopkimkimble.com", query='"Kim Kimble" hair'),
    P("Larry Sims", "Flawless by Gabrielle Union (co-founder)", "https://larryjsims.com", query='"Larry Sims" hair'),
    P("Kiyah Wright", "Celebrity hair stylist (Tyra Banks, Jennifer Hudson)", "https://www.kiyahwright.com",
      query='"Kiyah Wright" hair'),
    P("Felicia Leatherwood", "Love Your Tresses", "https://www.felicialeatherwood.com", query='"Felicia Leatherwood"'),
    P("Xia Charles", "Braided New York", "https://braidedny.com", query='"Xia Charles" braids OR hair'),
    P("Tym Wallace", "Celebrity hair stylist (Mary J. Blige, Taraji P. Henson)", "https://thetekniquegroup.com/tym-wallace/",
      query='"Tym Wallace" hair'),
    P("Neal Farinah", "Cécred (lead global stylist)", "https://mn2s.com/booking-agency/talent-roster/neal-farinah/", query='"Neal Farinah"'),
    P("Lacy Redway", "Celebrity hair stylist (Tessa Thompson, Tyla)", "https://www.lacyredway.com", query='"Lacy Redway"'),
    P("Nai'vasha Johnson", "Curl Queen", "https://curlqueenofficial.com", query='"Naivasha" OR "Nai\'vasha" hair',
      match=["Nai'vasha", "Nai’vasha", "Naivasha Johnson"], require=None),
    P("Yusef Williams", "Y by Yusef", "https://models.com/people/yusef", query='"Yusef Williams" hair'),
    P("Monaè Everett", "Monae Life Academy", "https://www.monaeeverett.com", query='"Monae Everett" OR "Monaè Everett"',
      match=["Monaè Everett", "Monae Everett"]),
    P("Tai Simon", "Celebrity hair stylist (Kelly Rowland, Zendaya)", "https://www.theonly.agency/artists/tai-simon", query='"Tai Simon" hair'),
    P("Greg Gilmore", "Celebrity hair stylist (Toni Braxton, Tiffany Haddish)", "https://greggilmorehair.com",
      query='"Greg Gilmore" hair'),
    P("Coree Moreno", "The Hair Prophet", "https://www.a-frameagency.com/artists/us/hair/coree-moreno", query='"Coree Moreno"'),
    P("Theo Barrett", "Celebrity hair stylist (Mary J. Blige, H.E.R.)", "https://www.instagram.com/tb_hairstylist/",
      query='"Theo Barrett" hair'),
    P("Johnny Wright", "Hair stylist to Michelle Obama", "http://www.kenbarboza.com/johnny-wright-biography/", query='"Johnny Wright" hair stylist'),
    P("Kellon Deryck", "The Kellon Deryck Salon (Atlanta)", "http://kellonderycksalon.com", query='"Kellon Deryck"'),
    P("Ricky Wing", "Celebrity hair stylist (Toni Braxton, Keke Palmer)", "https://models.com/people/ricky-wing",
      query='"Ricky Wing" hair'),
    P("Jawara Wauchope", "Celebrity hair stylist (Beyoncé, Erykah Badu)", "https://jawarawauchope.com",
      query='"Jawara" hair stylist', match=["Jawara Wauchope", "Jawara"]),
    P("Marcia Hamilton", "Celebrity hair stylist (Alicia Keys, Willow Smith)", "https://www.forwardartists.com/slideshow/artists-marcia-hamilton-portfolio",
      query='"Marcia Hamilton" hair'),
    P("Antoinette Hill", "Hair By Antoinette", "https://behindthechair.com/artist-profiles/antoinette-hill/", query='"Antoinette Hill" hair'),
    # ---- Barbers ---------------------------------------------------------------
    P("Kenny Duncan", "Main Attraction Unisex (Philadelphia)", "https://kennyduncan.com", query='"Kenny Duncan" barber'),
    P("Marcus Harvey", "BarberStar / The Musa Lair (Atlanta)", "https://musalair.com",
      query='"Marcus Harvey" barber OR "BarberStar"', match=["Marcus Harvey", "BarberStar"]),
    P("JC Tha Barber", "Celebrity barber (Los Angeles)", "", query='"JC Tha Barber"',
      match=["JC Tha Barber", "JC the Barber"]),
    # ---- Born outside the U.S. (their country is shown on the card) ----------
    P("Vernon François", "Vernon François Haircare", "https://www.vernonfrancois.com",
      query='"Vernon Francois" OR "Vernon François" hair', match=["Vernon François", "Vernon Francois"]),
    P("Mark Maciver", "SliderCuts (London)", "https://slidercuts.com",
      query='"SliderCuts" OR "Mark Maciver" barber', match=["SliderCuts", "Mark Maciver"]),
]

MAKEUP_PROS = [
    P("Sam Fine", "Fine Beauty", "https://www.instagram.com/samfinebeauty/", query='"Sam Fine" makeup'),
    P("AJ Crimson", "AJ Crimson Beauty (legacy)", "https://ajcrimson.com", query='"AJ Crimson"'),
    P("Sir John", "Celebrity makeup artist (Beyoncé)", "https://models.com/people/sir-john",
      query='"Sir John" makeup artist', match=["Sir John"]),
    P("Ashunta Sheriff", "Ashunta Sheriff Beauty", "https://ashuntabeauty.com",
      query='"Ashunta Sheriff"'),
    P("Danessa Myricks", "Danessa Myricks Beauty", "https://danessamyricksbeauty.com", query='"Danessa Myricks"'),
    P("Porsche Cooper", "Celebrity makeup artist (Iman, Beyoncé)", "https://www.porschecooper.com",
      query='"Porsche Cooper" makeup'),
    P("Keita Moore", "Celebrity makeup artist (Kelly Rowland, Iman)", "https://www.theonly.agency/artists/keita-moore", query='"Keita Moore" makeup'),
    P("Sheika Daley", "Celebrity makeup artist (Zendaya, Nicki Minaj)", "https://models.com/people/sheika-daley", query='"Sheika Daley"'),
    P("Camara Aunique", "Camara Aunique Beauty", "https://camaraauniquebeauty.com", query='"Camara Aunique"'),
    P("Bob Scott", "Celebrity makeup artist (Ashley Graham)", "", query='"Bob Scott" makeup'),
    P("Maxine Christians", "Celebrity makeup artist (Keke Palmer)", "http://www.maxinechristians.com", query='"Maxine Christians"'),
    P("Jackie Aina", "FORVR Mood", "https://forvrmood.com", query='"Jackie Aina"'),
    P("Shayla Mitchell", "MakeupShayla", "https://www.tiktok.com/@makeupshayla", query='"MakeupShayla" OR "Shayla Mitchell" makeup',
      match=["Shayla Mitchell", "MakeupShayla"]),
    P("Tasha Reiko Brown", "Celebrity makeup artist (Issa Rae)", "https://models.com/people/tasha-reiko-brown", query='"Tasha Reiko Brown"'),
    P("Tiyana Robinson", "Celebrity makeup artist", "http://www.tiyanarobinson.com", query='"Tiyana Robinson" makeup'),
    # ---- Born outside the U.S. (their country is shown on the card) ----------
    P("Mali Thomas", "Celebrity makeup artist (Marsai Martin)", "", query='"Mali Thomas" makeup'),
    P("Pat McGrath", "Pat McGrath Labs", "https://www.patmcgrath.com", query='"Pat McGrath" makeup'),
    P("Nyma Tang", "The Darkest Shade (YouTube)", "https://www.youtube.com/c/NymaTang", query='"Nyma Tang"'),
]


# =============================================================================
#  SECTION 3d — WHERE EACH PERSON IS FROM (shown on their card)
# =============================================================================
#  "Black American" = born in the U.S. with American Black lineage (not from
#  the African continent or another country). Everyone else shows their
#  country or heritage when it is publicly known. If someone is not listed
#  here, nothing is shown — their origin is not confirmed yet. To add one,
#  type their exact name and label below.
# -----------------------------------------------------------------------------

BLACK_AMERICAN = "Black American"
ORIGINS = {
    # ---- Black American (U.S. lineage, documented) ----
    "Christopher John Rogers": BLACK_AMERICAN, "LaQuan Smith": BLACK_AMERICAN,
    "Sergio Hudson": BLACK_AMERICAN, "Jerry Lorenzo": BLACK_AMERICAN,
    "Tremaine Emory": BLACK_AMERICAN, "Heron Preston": BLACK_AMERICAN,
    "Dapper Dan": BLACK_AMERICAN, "Pharrell Williams": BLACK_AMERICAN,
    "Don C": BLACK_AMERICAN, "Charles Harbison": BLACK_AMERICAN,
    "Aaron Potts": BLACK_AMERICAN, "Byron Lars": BLACK_AMERICAN,
    "Stephen Burrows": BLACK_AMERICAN, "April Walker": BLACK_AMERICAN,
    "Kimora Lee Simmons": BLACK_AMERICAN, "Russell Simmons": BLACK_AMERICAN,
    "Shawn Carter (Jay-Z), Damon Dash & Kareem Burke": BLACK_AMERICAN,
    "Sean Combs": BLACK_AMERICAN, "Kevan Hall": BLACK_AMERICAN,
    "Ye (Kanye West)": BLACK_AMERICAN, "Tracy Reese": BLACK_AMERICAN,
    "Maurice Malone": BLACK_AMERICAN, "Elisa Johnson": BLACK_AMERICAN,
    "Willi Smith": BLACK_AMERICAN, "Ann Lowe": BLACK_AMERICAN,
    "Arthur McGee": BLACK_AMERICAN, "Scott Barrie": BLACK_AMERICAN,
    "Zelda Wynn Valdes": BLACK_AMERICAN, "Jay Jaxon": BLACK_AMERICAN,
    "Patrick Kelly": BLACK_AMERICAN, "Elizabeth Keckley": BLACK_AMERICAN,
    "Edward Wilkerson": BLACK_AMERICAN,
    # ---- Born in another country ----
    "Victor Glemaud": "Born in Haiti", "Sebastien Amisial": "Born in Haiti",
    "Edvin Thompson": "Born in Jamaica", "Rachel Scott": "Born in Jamaica",
    "Karl Kani": "Born in Costa Rica", "Anifa Mvuemba": "Born in DR Congo",
    "Esé Azénabor": "Born in Nigeria", "Aurora James": "Born in Canada",
    "Rihanna": "Born in Barbados", "Omar Salam": "Senegal",
    "Vernon François": "United Kingdom", "Mark Maciver": "United Kingdom",
    "Pat McGrath": "United Kingdom", "Mali Thomas": "Nigeria",
    # ---- Born in the U.S. to immigrant family (heritage shown) ----
    "Telfar Clemens": "Liberian heritage", "Kerby Jean-Raymond": "Haitian heritage",
    "Felisha Noel": "Grenadian heritage", "Virgil Abloh": "Ghanaian heritage",
    "Tyler, the Creator": "Nigerian heritage", "Venny Etienne": "Haitian heritage",
    "Brandon Blackwood": "Jamaican heritage", "Maxwell Osborne": "Jamaican heritage",
    "Jason Rembert": "Martinican heritage",
    "Daymond John, J. Alexander Martin, Keith Perrin & Carl Brown": "Trinidadian heritage (Daymond John)",
    "Jackie Aina": "Nigerian heritage", "Nyma Tang": "South Sudanese heritage",
    "Marcia Hamilton": "Guyanese heritage",
}


# =============================================================================
#  SECTION 3c — THE THREE GALLERIES ON THE PAGE
# =============================================================================
#  Each gallery has its own list, its own Rolodex position, its own number of
#  slots and its own topic words for the backup check. Designers also have the
#  category drop-downs.
# -----------------------------------------------------------------------------

GROUPS = {
    "designers": {"label": "Fashion Designers",      "people": DESIGNERS,   "slots": CAROUSEL_SLOTS,
                  "words": FASHION_WORDS, "role": "designer",      "categories": True},
    "hair":      {"label": "Barbers & Hair Stylists", "people": HAIR_PROS,   "slots": GALLERY_SLOTS,
                  "words": HAIR_WORDS,    "role": "hair stylist",  "categories": False},
    "makeup":    {"label": "Makeup Artists",          "people": MAKEUP_PROS, "slots": GALLERY_SLOTS,
                  "words": MAKEUP_WORDS,  "role": "makeup artist", "categories": False},
}
for _key, _g in GROUPS.items():
    for _p in _g["people"]:
        _p["group"], _p["words"], _p["role"] = _key, _g["words"], _g["role"]
        _p["origin"] = ORIGINS.get(_p["name"], "")


# =============================================================================
#  SECTION 4 — SMALL HELPER TOOLS
# =============================================================================

def now_utc():
    """The current time, in universal time (UTC)."""
    return dt.datetime.now(dt.timezone.utc)


def log(msg):
    """Prints a line in the GitHub Actions log so you can see what happened."""
    print(f"[{now_utc().strftime('%H:%M:%S')}] {msg}", flush=True)


def clean_text(s):
    """Removes HTML tags and extra spaces from text found in news feeds."""
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def domain_of(url):
    """'https://www.essence.com/fashion/...' -> 'essence.com'"""
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def normalize_title(title):
    """Lower-case, strip punctuation and the ' - Source Name' tail, so the same
    headline is recognised even if punctuation differs slightly."""
    t = re.sub(r"\s[-|–—]\s[^-|–—]+$", "", title or "")
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def mentions_designer(designer, text):
    """True if at least one 'match' word appears as a whole word or phrase.
    Example: 'Don C' matches 'Don C collab' but NOT 'Don Cheadle'."""
    for term in designer["match"]:
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text):
            return True
    return False


def http_get(url):
    """Downloads a web page. Returns the text, or None if anything fails.
    (Failures are normal — the script simply moves on.)"""
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT},
                         timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return r.text, r.url
    except Exception as e:
        log(f"   could not open {url[:80]} ({type(e).__name__})")
    return None, None


# =============================================================================
#  SECTION 5 — SEARCHING THE NEWS FEEDS
# =============================================================================
#  Two free public news feeds are used (no account or API key needed):
#    A) Bing News RSS   — usually includes the real article link + a picture
#    B) Google News RSS — used only when Bing finds nothing
#  Only articles from the last LOOKBACK_HOURS that actually mention the
#  designer are kept. Results come back newest first.
# -----------------------------------------------------------------------------

def _child_text(item, suffix):
    """Reads a field from a feed item, ignoring XML namespace prefixes."""
    for child in item:
        if child.tag.split("}")[-1].lower() == suffix.lower():
            return (child.text or "").strip(), child
    return "", None


def _real_link_from_bing(link):
    """Bing hides the real address inside its own links, in two styles:
       old:  bing.com/news/apiclick.aspx?...&url=https%3a%2f%2fsite.com%2f...
       new:  bing.com/ck/a?!&&p=...&u=a1aHR0cHM6Ly9zaXRlLmNvbS8...
             ("a1" + the address in base64 code)
    This unpacks either one and returns the actual article address."""
    import base64
    try:
        parsed = urlparse(link)
        if "bing.com" not in parsed.netloc:
            return link
        qs = parse_qs(parsed.query)
        if "url" in qs:
            return unquote(qs["url"][0])
        if "u" in qs:
            code = qs["u"][0]
            if code.startswith("a1"):
                code = code[2:]
            real = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode("utf-8")
            if real.startswith("http"):
                return real
    except Exception:
        pass
    return link


def search_bing(designer):
    url = ("https://www.bing.com/news/search?format=rss&qft=sortbydate%3d%221%22"
           "&setlang=en-us&cc=US&mkt=en-US"          # English-language US news
           f"&q={quote_plus(designer['query'])}")
    text, _ = http_get(url)
    if not text:
        return []
    results = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return []
    for item in root.iter("item"):
        title, _ = _child_text(item, "title")
        link, _ = _child_text(item, "link")
        desc, _ = _child_text(item, "description")
        pub, _ = _child_text(item, "pubDate")
        source, _ = _child_text(item, "Source")
        image, _ = _child_text(item, "Image")
        real = _real_link_from_bing(link)
        results.append({
            "headline": clean_text(title),
            "url": real,
            "summary": clean_text(desc)[:240],
            "published": pub,
            "source": source or domain_of(real),
            "feed_image": image or "",
        })
    return results


def search_google(designer):
    q = quote_plus(designer["query"] + " when:2d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    text, _ = http_get(url)
    if not text:
        return []
    results = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return []
    for item in root.iter("item"):
        title, _ = _child_text(item, "title")
        link, _ = _child_text(item, "link")
        desc, _ = _child_text(item, "description")
        pub, _ = _child_text(item, "pubDate")
        source, src_el = _child_text(item, "source")
        source_site = src_el.get("url", "") if src_el is not None else ""
        results.append({
            "headline": clean_text(title),
            "url": link,                         # Google redirect link; opens
            "summary": clean_text(desc)[:240],   # the article for visitors
            "published": pub,
            "source": source or domain_of(source_site),
            "source_site": source_site,
            "feed_image": "",
        })
    return results


def find_todays_articles(designer):
    """Returns this designer's articles from roughly the last day, newest first,
    keeping only articles that really mention them."""
    found = search_bing(designer) or search_google(designer)
    cutoff = now_utc() - dt.timedelta(hours=LOOKBACK_HOURS)
    keep = []
    for a in found:
        try:
            when = parsedate_to_datetime(a["published"])
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue                                   # no date = can't tell if today
        if when < cutoff:
            continue                                   # too old
        if not mentions_designer(designer, a["headline"] + " " + a["summary"]):
            continue                                   # not really about them
        a["published_iso"] = when.astimezone(dt.timezone.utc).isoformat()
        keep.append(a)
    keep.sort(key=lambda a: a["published_iso"], reverse=True)
    return keep


# =============================================================================
#  SECTION 6 — BACKUP CHECK: ARTICLE, PHOTO AND WEBSITE VERIFICATION
# =============================================================================
#  Nothing is posted until it passes these checks.
#
#  6a  fetch_page ........ opens a web page once (remembered for the run)
#  6b  verify_article .... link works + article names the designer + fashion
#  6c  photo candidates .. every photo on the article page, ranked:
#                            1st  photos whose caption / alt text / file name
#                                 names the designer or brand
#                            2nd  the article's main share photo
#                            3rd  the news feed's thumbnail
#  6d  check_photo ....... the photo really loads, is a photo (not a logo or
#                          icon), is big enough and not a banner strip
#  6e  choose_photo ...... picks the highest-ranked photo that passes, and
#                          never repeats a photo already in the carousel
#  6f  designer website .. checks the website link opens; finds a checked
#                          photo from it for "spotlight" cards
#  6g  check report ...... records every pass / fail with the reason
# -----------------------------------------------------------------------------

from urllib.parse import urljoin

TEST_MODE = False            # switched on by --test (skips internet checks)
_page_cache = {}
_photo_cache = {}
_site_cache = {}
_site_photo_cache = {}
_publisher_default_cache = {}
CHECK_REPORT = {"articles": [], "websites": [], "rechecked": [], "photos": []}


# ---- 6a. Open a page once -----------------------------------------------------
def fetch_page(url):
    """Returns {"status", "url" (after redirects), "type", "html"} or None."""
    if not url:
        return None
    if url in _page_cache:
        return _page_cache[url]
    import requests
    page = None
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                       "Accept-Language": "en-US,en;q=0.9"},
                         timeout=REQUEST_TIMEOUT, allow_redirects=True)
        ctype = r.headers.get("Content-Type", "").lower()
        page = {"status": r.status_code, "url": r.url, "type": ctype,
                "html": r.text if "html" in ctype else ""}
    except Exception as e:
        log(f"   could not open {url[:80]} ({type(e).__name__})")
    _page_cache[url] = page
    return page


def page_text(page_html):
    """The readable words of a page, without menus, scripts and styles."""
    s = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|form)[^>]*>.*?</\1>", " ", page_html)
    return clean_text(s)


# ---- 6b. Is this article real, and about the right person? -------------------
BLOCKED_HOSTS = ("news.google.com", "bing.com", "consent.google.com")

def verify_article(article, designer):
    """Returns (passed: bool, reason: str, page)."""
    article["url"] = _real_link_from_bing(article["url"])
    page = fetch_page(article["url"])
    if not page:
        return False, "link did not open", None
    if page["status"] != 200:
        return False, f"link returned error {page['status']}", page
    if any(domain_of(page["url"]).endswith(h) for h in BLOCKED_HOSTS):
        return False, "could not reach the original article to check it", page
    if not page["html"]:
        return False, "link is not a web page", page
    lang = article_language(page["html"])
    if lang and not lang.startswith("en"):
        return False, f"article is not in English (language: {lang})", page
    text = page_text(page["html"])
    if len(text) < 400:
        return False, "page has almost no article text (paywall or blocked)", page
    if not mentions_designer(designer, text):
        return False, "article text does not name this designer or brand", page
    if designer.get("require") and not any(
            re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text) for t in designer["require"]):
        return False, "article does not also name " + " / ".join(designer["require"]), page
    if not fashion_near_name(designer, text):
        return False, (f"no {designer.get('role', 'designer')} talk near the name "
                       "(likely a different person)"), page
    return True, "article verified", page


def article_language(page_html):
    """The page's declared language, e.g. 'en', 'en-us', 'fr' ('' if unknown)."""
    for pattern in (r'<html\b[^>]*\blang\s*=\s*["\']([a-zA-Z_-]+)',
                    r'<meta[^>]+property=["\']og:locale["\'][^>]+content=["\']([a-zA-Z_-]+)',
                    r'<meta[^>]+http-equiv=["\']content-language["\'][^>]+content=["\']([a-zA-Z_-]+)'):
        m = re.search(pattern, page_html, re.I)
        if m:
            return m.group(1).lower().replace("_", "-")
    return ""


def fashion_near_name(designer, text):
    """True if, somewhere the designer's name or brand appears, at least
    FASHION_WORDS_NEEDED different fashion words appear close by (within
    NEAR_NAME_CHARACTERS). A tennis article that happens to mention "style"
    at the bottom of the page will not pass."""
    lower = text.lower()
    for term in designer["match"]:
        for m in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text):
            window = lower[max(0, m.start() - NEAR_NAME_CHARACTERS): m.end() + NEAR_NAME_CHARACTERS]
            found = {w for w in designer.get("words", FASHION_WORDS)
                     if re.search(r"(?<!\w)" + re.escape(w), window)}
            if len(found) >= FASHION_WORDS_NEEDED:
                return True
    return False


# ---- 6c. Every photo on the page, best first ---------------------------------
def _attr(tag, name):
    m = re.search(r'\b' + name + r'\s*=\s*["\']([^"\']+)["\']', tag, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def _largest_from_srcset(srcset):
    best, best_w = "", 0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = int(re.sub(r"\D", "", bits[1]) or 0) if len(bits) > 1 and bits[1].endswith("w") else 0
        if w >= best_w:
            best, best_w = bits[0], w
    return best


def _name_slugs(designer):
    """'Sergio Hudson' -> 'sergio-hudson', 'sergiohudson' (to spot file names)."""
    slugs = set()
    for term in designer["match"] + [designer["brand"]]:
        t = re.sub(r"[^a-z0-9 ]", "", term.lower()).strip()
        if len(t) >= 5:
            slugs.update({t.replace(" ", "-"), t.replace(" ", "_"), t.replace(" ", "")})
    return slugs


def photo_candidates(article, designer, page):
    """List of (score, photo_address, where_it_came_from), best first."""
    found = {}
    def add(url, score, why):
        if not url or url.startswith("data:"):
            return
        url = urljoin(page["url"], url) if page else url
        if url.startswith("//"):
            url = "https:" + url
        if url not in found or found[url][0] < score:
            found[url] = (score, why)

    if page and page.get("html"):
        h = page["html"]
        slugs = _name_slugs(designer)

        # photos inside <figure> blocks, judged by their caption
        for fig in re.findall(r"(?is)<figure\b.*?</figure>", h):
            cap = clean_text(" ".join(re.findall(r"(?is)<figcaption\b.*?</figcaption>", fig)))
            for tag in re.findall(r"(?is)<img\b[^>]*>", fig):
                src = (_largest_from_srcset(_attr(tag, "srcset") or _attr(tag, "data-srcset"))
                       or _attr(tag, "data-src") or _attr(tag, "src"))
                alt = _attr(tag, "alt")
                if mentions_designer(designer, cap + " " + alt):
                    add(src, 30, "captioned with the designer's name")

        # every other photo, judged by its alt text or file name
        for tag in re.findall(r"(?is)<img\b[^>]*>", h):
            src = (_largest_from_srcset(_attr(tag, "srcset") or _attr(tag, "data-srcset"))
                   or _attr(tag, "data-src") or _attr(tag, "src"))
            if not src:
                continue
            alt = _attr(tag, "alt")
            if mentions_designer(designer, alt):
                add(src, 25, "alt text names the designer")
            elif any(sl in src.lower() for sl in slugs):
                add(src, 20, "file name names the designer")

        # the article's main share photo
        for prop in ("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"):
            for tag in re.findall(r"(?is)<meta\b[^>]*>", h):
                if (_attr(tag, "property").lower() == prop or _attr(tag, "name").lower() == prop):
                    add(_attr(tag, "content"), 10, "article's main photo")

    if article.get("feed_image"):
        add(article["feed_image"], 5, "news feed thumbnail")

    return sorted(((s, u, w) for u, (s, w) in found.items()), key=lambda x: -x[0])


# ---- 6d. Does this photo really work, and is it a real photo? ----------------
def check_photo(url):
    """Returns (passed: bool, reason: str)."""
    if url in _photo_cache:
        return _photo_cache[url]
    result = _check_photo(url)
    _photo_cache[url] = result
    return result


def _check_photo(url):
    path = urlparse(url).path.lower()
    if any(w in path for w in BAD_PHOTO_WORDS):
        return False, "looks like a logo, icon or placeholder"
    if path.endswith((".svg", ".gif", ".ico")):
        return False, "not a photo (svg/gif/icon)"
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, stream=True)
        if r.status_code != 200:
            return False, f"photo did not load (error {r.status_code})"
        ctype = r.headers.get("Content-Type", "").lower()
        if not ctype.startswith("image/") or "svg" in ctype or "gif" in ctype:
            return False, f"not a photo ({ctype or 'unknown type'})"
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) >= 600_000:
                break
        r.close()
    except Exception as e:
        return False, f"photo did not load ({type(e).__name__})"

    size = None
    try:
        from io import BytesIO
        from PIL import Image
        size = Image.open(BytesIO(data)).size
    except Exception:
        size = None
    if size:
        w, h = size
        if min(w, h) < MIN_PHOTO_SIDE:
            return False, f"too small ({w}x{h})"
        if max(w, h) / max(1, min(w, h)) > MAX_PHOTO_RATIO:
            return False, f"banner-shaped, not a photo ({w}x{h})"
        return True, f"photo checked ({w}x{h})"
    if len(data) < 40_000:
        return False, "photo size could not be confirmed and the file is tiny"
    return True, "photo loads (size not readable)"


def publisher_default_photo(article_url):
    """The picture a publisher uses on its home page; if an article uses the
    same one, it is a generic graphic, not a photo of the designer."""
    dom = domain_of(article_url)
    if dom not in _publisher_default_cache:
        page = fetch_page(f"https://{dom}/")
        img = ""
        if page and page.get("html"):
            for tag in re.findall(r"(?is)<meta\b[^>]*>", page["html"]):
                if _attr(tag, "property").lower() == "og:image":
                    img = urljoin(page["url"], _attr(tag, "content"))
                    break
        _publisher_default_cache[dom] = img
    return _publisher_default_cache[dom]


# ---- 6e. Pick the best photo that passes -------------------------------------
def choose_photo(article, designer, page, used_photos):
    """Returns (photo_address or "", note, list_of_rejected_photos)."""
    rejected = []
    generic = publisher_default_photo(page["url"] if page else article["url"])
    for score, url, why in photo_candidates(article, designer, page):
        if url in used_photos:
            rejected.append({"photo": url, "reason": "already showing in the carousel"})
            continue
        if generic and url == generic:
            rejected.append({"photo": url, "reason": "publisher's generic share picture"})
            continue
        ok, reason = check_photo(url)
        if ok:
            return url, f"{why}; {reason}", rejected
        rejected.append({"photo": url, "reason": reason})
    found, source = person_photo(designer, used_photos)
    if found:
        return found, f"no usable article photo; used a photo of them from {domain_of(source)}", rejected
    return "", "no usable photo found", rejected


# ---- 6f. The designer's website ----------------------------------------------
#  Most people in the lists already have a checked website (researched
#  November 2026). If someone has none, or theirs stops working, the script
#  looks one up the way a person would on Google, ONCE, and remembers it in
#  the memory file. It tries, in order:
#    1. Wikidata — the public knowledge base behind search "knowledge panels";
#       it records many people's official website.
#    2. DuckDuckGo web search, then Bing web search, for their official site.
#    3. Agency portfolio pages (A-Frame, The Only Agency, Forward Artists,
#       Models.com and others). Stylists and makeup artists often have these
#       instead of a website, and they are full of photos of their work.
#  A result is only accepted when ALL of these are true:
#    - the web address contains their name or brand (e.g. "kimkimble" in
#      shopkimkimble.com), OR it is a known agency page about them,
#    - it is not a news, shopping or social media site,
#    - the page opens and names them.
#  Found sites are listed in data/checks.json as "FOUND AUTOMATICALLY" so you
#  can copy them into the lists. If nothing is found, it tries again in
#  30 days, and the card's link opens a Google search for them instead.

SITE_STATE = {}          # filled from the memory file when the run starts
LOOKUP_RETRY_DAYS = 30
NOT_OFFICIAL_SITES = (
    "instagram.", "facebook.", "twitter.", "x.com", "tiktok.", "linkedin.", "pinterest.",
    "youtube.", "threads.", "wikipedia.", "wikidata.", "imdb.", "amazon.", "etsy.",
    "ebay.", "poshmark.", "depop.", "grailed.", "nordstrom.", "saksfifthavenue.", "ssense.",
    "farfetch.", "net-a-porter.", "revolve.", "shopbop.", "vogue.", "wwd.", "essence.",
    "elle.", "harpersbazaar.", "thecut.", "nytimes.", "complex.", "hypebeast.", "highsnobiety.",
    "forbes.", "bing.", "google.", "duckduckgo.", "yelp.", "crunchbase.", "zoominfo.",
    "bloomberg.", "rocketreach.", "signalhire.", "contactout.", "famousbirthdays.",
    "voyage", "canvasrebel.", "shoutout", "stylectory.", "modadatabase.", "lyst.",
    "thecoolhour.", "therealreal.", "fashionmodeldirectory.", "runway360.", "booksy.",
)
# Agency / portfolio sites accepted when the page is about the person
AGENCY_SITES = (
    "models.com/people", "a-frameagency.com/artists", "theonly.agency/artists",
    "forwardartists.com", "thewallgroup.com", "mn2s.com/booking-agency",
    "thetekniquegroup.com", "cloutierremix.com", "exclusiveartists.com",
    "opusbeauty.com", "starworksartists.com", "honeyartists.com", "kenbarboza.com",
    "behindthechair.com/artist-profiles", "tracey-mattingly.com", "streetersagency.com",
    "art-dept.com", "jedroot.com", "thecanvasagency.com",
)
_NAME_SUFFIXES = (" new york", " nyc", " studio", " designs", " design", " collection",
                  " fashions", " fashion", " the label", " paris", " america", " of harlem",
                  " beauty", " hair", " salon", " (legacy)")


def _slug(text):
    """"L'enchanteur" -> "lenchanteur";  "Kevan Hall Designs" -> "kevanhalldesigns" """
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def _site_slugs(designer):
    """Words a person's own web address would contain."""
    out = set()
    brand = re.sub(r"\(.*?\)", "", designer["brand"])          # drop "(Rihanna, ...)" notes
    for part in brand.split(" / "):
        b = part.lower().strip()
        if not b.startswith("celebrity "):
            out.add(_slug(b))
            for suffix in _NAME_SUFFIXES:
                if b.endswith(suffix):
                    out.add(_slug(b[: -len(suffix)]))
    if not re.search(r"[&,(]", designer["name"]):
        out.add(_slug(designer["name"]))
        words = [w for w in re.split(r"\s+", designer["name"]) if len(w) > 1 or w.isalpha()]
        if len(words) >= 3:                                      # "Simone I. Smith" -> "simonesmith"
            out.add(_slug(words[0] + words[-1]))
    for m in designer["match"]:
        out.add(_slug(m))
    return {x for x in out if len(x) >= 5}


def _homepage(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _is_agency_page(url):
    low = url.lower()
    return any(a in low for a in AGENCY_SITES)


def _looks_official(url, designer):
    if _is_agency_page(url):
        return True
    host = urlparse(url).netloc.lower()
    if any(bad in host for bad in NOT_OFFICIAL_SITES):
        return False
    host_slug = _slug(host)
    return any(s in host_slug for s in _site_slugs(designer))


def _site_names_designer(page, designer):
    if not page or page["status"] != 200 or not page["html"]:
        return False
    head = page["html"][:200_000].lower()
    names = [designer["name"].lower()] + [m.lower() for m in designer["match"]]
    if not designer["brand"].lower().startswith("celebrity "):
        names.append(re.sub(r"\s*\(.*?\)", "", designer["brand"]).lower())
    names += [n.replace("'", "’") for n in names]
    return any(n and n in head for n in names) or any(s in _slug(head[:20_000]) for s in _site_slugs(designer))


def _accept(link, designer):
    """Returns the address to keep for this search result, or ""."""
    if not link.startswith("http") or not _looks_official(link, designer):
        return ""
    if _is_agency_page(link):                     # keep the exact profile page
        return link if _site_names_designer(fetch_page(link), designer) else ""
    home = _homepage(link)
    if _site_names_designer(fetch_page(home), designer):
        return home
    if _site_names_designer(fetch_page(link), designer):
        return home
    return ""


def _search_terms(designer):
    role = designer.get("role", "designer")
    brand = re.sub(r"\s*\(.*?\)", "", designer["brand"])
    if role == "designer":
        return [f'"{brand}" official site', f'"{designer["name"]}" {brand} designer website']
    return [f'"{designer["name"]}" {role} official website',
            f'"{designer["name"]}" {role} agency portfolio']


def _wikidata_site(designer):
    """Official website recorded for this person (or brand) in Wikidata."""
    import requests
    words = designer.get("words", FASHION_WORDS)
    for label in (designer["name"], re.sub(r"\s*\(.*?\)", "", designer["brand"])):
        try:
            r = requests.get("https://www.wikidata.org/w/api.php", timeout=REQUEST_TIMEOUT,
                             headers={"User-Agent": USER_AGENT},
                             params={"action": "wbsearchentities", "search": label,
                                     "language": "en", "format": "json", "limit": 5})
            for hit in r.json().get("search", []):
                desc = (hit.get("description") or "").lower()
                if not any(w in desc for w in words + ["designer", "stylist", "artist", "brand", "company"]):
                    continue
                e = requests.get("https://www.wikidata.org/wiki/Special:EntityData/"
                                 f"{hit['id']}.json", timeout=REQUEST_TIMEOUT,
                                 headers={"User-Agent": USER_AGENT}).json()
                claims = e["entities"][hit["id"]].get("claims", {})
                for c in claims.get("P856", []):          # P856 = official website
                    url = c["mainsnak"].get("datavalue", {}).get("value", "")
                    if url and _site_names_designer(fetch_page(url), designer):
                        return url.rstrip("/")
        except Exception:
            continue
    return ""


# ---- Reading a search results page ------------------------------------------
#  The script opens the SAME Bing results page a person sees (bing.com/search),
#  reads every result on it (title, link, short description), and then opens
#  those result links to find the person's website, Instagram and photos.
#  DuckDuckGo's results page is read too, as a second opinion.

_search_cache = {}
SKIP_RESULT_HOSTS = ("bing.com", "microsoft.com", "msn.com/en-us/feed", "go.microsoft",
                     "duckduckgo.com", "google.com/search")


def _clean_result_link(href):
    href = html.unescape(href or "").strip()
    href = _real_link_from_bing(href)
    if "uddg=" in href:
        href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
    return href if href.startswith("http") else ""


def bing_results(query):
    """Every result on Bing's normal results page: [{url, title, snippet}]."""
    key = ("bing", query)
    if key in _search_cache:
        return _search_cache[key]
    url = ("https://www.bing.com/search?setlang=en-US&cc=US&count=20&q=" + quote_plus(query))
    page = fetch_page(url)
    text = (page or {}).get("html", "")
    results = []
    # each result is an <li class="b_algo"> block: <h2><a href=LINK>TITLE</a></h2> ... <p>DESCRIPTION</p>
    for chunk in re.split(r'<li class="b_algo"', text)[1:]:
        chunk = chunk.split('<li class="b_algo"')[0][:20000]
        m = re.search(r'(?is)<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', chunk)
        if not m:
            continue
        link = _clean_result_link(m.group(1))
        snip = re.search(r'(?is)<p[^>]*>(.*?)</p>', chunk)
        if link:
            results.append({"url": link, "title": clean_text(m.group(2)),
                            "snippet": clean_text(snip.group(1)) if snip else ""})
        # extra links shown under a result (e.g. "About", "Contact", "Shop")
        for extra in re.findall(r'(?is)<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', chunk)[1:6]:
            l2 = _clean_result_link(extra[0])
            if l2 and not any(h in l2 for h in SKIP_RESULT_HOSTS):
                results.append({"url": l2, "title": clean_text(extra[1]), "snippet": ""})
    # if Bing changed its page layout, fall back to every outside link on the page
    if not results and text:
        for href, label in re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text):
            link = _clean_result_link(href)
            if link and not any(h in link for h in SKIP_RESULT_HOSTS):
                results.append({"url": link, "title": clean_text(label), "snippet": ""})
    if not results:
        log(f"   Bing results page gave no links for: {query}"
            + ("" if text else " (page did not open)"))
    _search_cache[key] = _dedupe(results)
    return _search_cache[key]


def duckduckgo_results(query):
    """Every result on DuckDuckGo's results page: [{url, title, snippet}]."""
    key = ("ddg", query)
    if key in _search_cache:
        return _search_cache[key]
    page = fetch_page("https://html.duckduckgo.com/html/?q=" + quote_plus(query))
    text = (page or {}).get("html", "")
    results = []
    for chunk in re.split(r'class="result results_links', text)[1:]:
        m = re.search(r'(?is)class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', chunk)
        if not m:
            continue
        snip = re.search(r'(?is)class="result__snippet"[^>]*>(.*?)</a>', chunk)
        link = _clean_result_link(m.group(1))
        if link:
            results.append({"url": link, "title": clean_text(m.group(2)),
                            "snippet": clean_text(snip.group(1)) if snip else ""})
    _search_cache[key] = _dedupe(results)
    return _search_cache[key]


def _dedupe(results):
    seen, out = set(), []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            out.append(r)
    return out


def web_results(query):
    """Bing's results first, then DuckDuckGo's, without repeats."""
    return _dedupe(bing_results(query) + duckduckgo_results(query))


# (older names, still used elsewhere in the script)
def _bing_links(query):
    return [r["url"] for r in bing_results(query)]


def _duckduckgo_links(query):
    return [r["url"] for r in duckduckgo_results(query)]


def find_instagram(designer):
    """The person's Instagram profile, picked from the search results: an
    instagram.com/<name> link whose title or description names them."""
    name = designer["name"]
    memory = SITE_STATE.setdefault(name, {})
    if "instagram" in memory:
        return memory["instagram"]
    found = ""
    if not TEST_MODE:
        for q in (details_query(designer), f'{designer["name"]} instagram'):
            for r in web_results(q):
                u = urlparse(r["url"])
                parts = [x for x in u.path.split("/") if x]
                if ("instagram.com" in u.netloc and len(parts) == 1
                        and parts[0] not in ("p", "reel", "reels", "explore", "accounts", "stories")
                        and mentions_designer(designer, r["title"] + " " + r["snippet"])):
                    found = f"https://www.instagram.com/{parts[0]}/"
                    break
            if found:
                break
    memory["instagram"] = found
    if found:
        log(f"   found Instagram for {name}: {found}")
    return found


def look_up_site(designer):
    """Finds a person's official website or agency page by reading the search
    results pages and opening the links on them. "" if none passes."""
    found = _wikidata_site(designer)
    if found:
        return found
    for query in [details_query(designer)] + _search_terms(designer):
        for r in web_results(query)[:20]:
            kept = _accept(r["url"], designer)
            if kept:
                return kept
    return ""


def verified_site(designer):
    """The designer's working website: the one in the list if it opens,
    otherwise one found automatically, otherwise "" (a search link is used)."""
    name = designer["name"]
    if name in _site_cache:
        return _site_cache[name]
    if TEST_MODE:
        _site_cache[name] = designer["site"]
        return designer["site"]

    site, note = "", ""
    if designer["site"]:
        page = fetch_page(designer["site"])
        if page and page["status"] == 200 and page["html"]:
            site, note = designer["site"], "opens"
        elif any(h in designer["site"] for h in ("instagram.", "facebook.", "tiktok.", "x.com/")):
            # social sites often block automated visits; keep the listed profile
            site, note = designer["site"], "social profile kept (these sites block automated checks)"
        else:
            note = "listed website did NOT open"

    if not site:
        remembered = SITE_STATE.get(name, {})
        retry_after = (now_utc() - dt.timedelta(days=LOOKUP_RETRY_DAYS)).date().isoformat()
        if remembered.get("site"):
            site = remembered["site"]
            note = (note + "; " if note else "") + "using website found earlier"
        elif remembered.get("looked", "") < retry_after:
            found = look_up_site(designer)
            SITE_STATE[name] = {"site": found, "looked": now_utc().date().isoformat()}
            if found:
                site = found
                note = (note + "; " if note else "") + "FOUND AUTOMATICALLY — add it to the designer list"
                log(f"   found website for {name}: {found}")
            else:
                note = (note + "; " if note else "") + "no official website found — using a search link"
        else:
            note = (note + "; " if note else "") + "no website (looked recently) — using a search link"

    _site_cache[name] = site
    CHECK_REPORT["websites"].append({"designer": name, "website": site or "(none)", "result": note})
    return site


def designer_site_photo(designer):
    """A checked photo from the designer's own website (for spotlight cards)."""
    name = designer["name"]
    if name not in _site_photo_cache:
        photo = ""
        site = verified_site(designer)
        if site and not TEST_MODE:
            page = fetch_page(site)
            for score, url, why in photo_candidates({}, designer, page):
                if check_photo(url)[0]:
                    photo = url
                    break
        _site_photo_cache[name] = photo
    return _site_photo_cache[name]


# ---- 6h. Finding a photo of the person from search results --------------------
#  Uses the SAME search as the card's "Get details" link, so the photos come
#  from the pages a person sees when they search the name. In order:
#    1. a checked photo from their own website or agency page
#    2. an IMAGE SEARCH for the person — a photo is only used if the page it
#       comes from names the person with topic words nearby (fashion / hair /
#       makeup), and the photo passes the photo check (not a logo, big enough…)
#    3. the web search result pages — photos captioned with their name first
#  The photo's source page is kept so the card can credit and link to it.
#  Found photos are remembered for PHOTO_REFRESH_DAYS, then looked up again.

def details_query(designer):
    """The original search words: "<brand> <name> designer", or for stylists
    and makeup artists "<name> <role>"."""
    role = designer.get("role", "designer")
    if role == "designer":
        return f'{designer["brand"]} {designer["name"]} designer'
    return f'{designer["name"]} {role}'


def details_link(designer):
    return DETAILS_SEARCH + quote_plus(details_query(designer))


def _page_is_about(designer, page):
    """True if a result page names the person with topic words nearby."""
    if not page or page.get("status") != 200 or not page.get("html"):
        return False
    text = page_text(page["html"])
    return mentions_designer(designer, text) and fashion_near_name(designer, text)


def _image_search(designer):
    """Bing image search: list of (photo address, page it appears on)."""
    q = f'"{designer["name"]}" {designer.get("role", "designer")}'
    text, _ = http_get("https://www.bing.com/images/search?form=HDRSC3&first=1&q=" + quote_plus(q))
    found = []
    for m in re.findall(r'class="iusc"[^>]*\bm="([^"]+)"', text or ""):
        try:
            data = json.loads(html.unescape(m))
            if data.get("murl") and data.get("purl"):
                found.append((data["murl"], data["purl"]))
        except Exception:
            continue
    return found


def person_photo(designer, used_photos=()):
    """Returns (photo address, page it came from) — or ("", "")."""
    if TEST_MODE:
        return "", ""
    name = designer["name"]
    memory = SITE_STATE.setdefault(name, {})
    fresh_after = (now_utc() - dt.timedelta(days=PHOTO_REFRESH_DAYS)).date().isoformat()
    if (memory.get("photo") and memory.get("photo_date", "") >= fresh_after
            and memory["photo"] not in used_photos and check_photo(memory["photo"])[0]):
        return memory["photo"], memory.get("photo_source", "")

    photo, source, how = "", "", ""
    # 1. own website / agency page
    site_photo = designer_site_photo(designer)
    if site_photo and site_photo not in used_photos:
        photo, source, how = site_photo, verified_site(designer), "their website"
    # 2. image search
    if not photo:
        for img, page_url in _image_search(designer)[:15]:
            if img in used_photos or not check_photo(img)[0]:
                continue
            if _page_is_about(designer, fetch_page(page_url)):
                photo, source, how = img, page_url, "image search"
                break
    # 3. web search result pages
    if not photo:
        for r in web_results(details_query(designer))[:12]:
            link = r["url"]
            if any(h in link for h in ("instagram.", "facebook.", "tiktok.", "x.com/", "twitter.")):
                continue                     # social pages hide photos from scripts
            page = fetch_page(link)
            if not _page_is_about(designer, page):
                continue
            for score, url, why in photo_candidates({}, designer, page):
                if score >= 10 and url not in used_photos and check_photo(url)[0]:
                    photo, source, how = url, page["url"], "search result: " + why
                    break
            if photo:
                break

    memory.update({"photo": photo, "photo_source": source,
                   "photo_date": now_utc().date().isoformat()})
    CHECK_REPORT["photos"].append({"person": name, "photo": photo or "(none found)",
                                   "from": source, "how": how})
    if photo:
        log(f"   photo for {name} from {how}: {domain_of(source)}")
    return photo, source


# ---- 6g. Check report ---------------------------------------------------------
def report(designer, article, result, reason, photo="", photo_note="", rejected_photos=None):
    CHECK_REPORT["articles"].append({
        "gallery": designer.get("group", "designers"),
        "designer": designer["name"], "brand": designer["brand"],
        "headline": article.get("headline", ""), "source": article.get("source", ""),
        "url": article.get("url", ""), "result": result, "reason": reason,
        "photo": photo, "photo_note": photo_note,
        "rejected_photos": rejected_photos or [],
    })
    log(f"   {result.upper()}: {reason}" + (f" | photo: {photo_note}" if photo_note else ""))


# =============================================================================
#  SECTION 7 — THE MEMORY FILE (data/state.json)
# =============================================================================
#  posted   : { "source|headline" : date posted }  -> prevents re-posting
#  next     : number of the designer to search first tomorrow
#  carousel : the 10 posts currently in the carousel
#  cats     : the 5 posts currently in each category drop-down
#  sites    : websites found automatically (and when it last looked)
#  groups   : for the hair and makeup galleries, each one's own
#             { "next": Rolodex position, "carousel": its 4 slots }
#  (The designer gallery keeps "next", "carousel" and "cats" at the top.)
# -----------------------------------------------------------------------------

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    else:
        s = {}
    s.setdefault("posted", {})
    s.setdefault("next", 0)
    s.setdefault("carousel", [None] * CAROUSEL_SLOTS)
    s.setdefault("cats", {})
    s.setdefault("sites", {})        # websites found automatically (Section 6f)
    s["carousel"] = (s["carousel"] + [None] * CAROUSEL_SLOTS)[:CAROUSEL_SLOTS]
    for key in CATEGORIES:
        size = category_size(key)
        s["cats"][key] = (s["cats"].get(key, []) + [None] * size)[:size]
    s["next"] = s["next"] % len(DESIGNERS)
    s.setdefault("groups", {})
    for key, g in GROUPS.items():
        if key == "designers":
            continue
        gs = s["groups"].setdefault(key, {})
        gs.setdefault("next", 0)
        gs["next"] = gs["next"] % len(g["people"])
        gs["carousel"] = (gs.get("carousel", []) + [None] * g["slots"])[:g["slots"]]
    cutoff = (now_utc() - dt.timedelta(days=REMEMBER_POSTED_DAYS)).date().isoformat()
    s["posted"] = {k: v for k, v in s["posted"].items() if v >= cutoff}
    return s


def group_state(state, key):
    """The part of the memory file that belongs to one gallery."""
    return state if key == "designers" else state["groups"][key]


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def category_size(key):
    """A category shows 5 designers, or fewer if fewer designers belong to it
    (e.g. Swimwear & Lingerie has 3), so no slot is ever empty."""
    members = sum(1 for d in DESIGNERS if key in d["cats"])
    return min(CATEGORY_SLOTS, members)


def memory_key(article):
    """Same headline from the SAME source = same key (skipped).
    Same story from a DIFFERENT source = different key (allowed)."""
    src = (article.get("source") or domain_of(article["url"])).lower()
    return f"{src}|{normalize_title(article['headline'])}"


# =============================================================================
#  SECTION 8 — THE DAILY ROLODEX RUN (main logic)
# =============================================================================
#  8a make_post ........... builds one card for the website
#  8b place_in_category ... puts a card into a drop-down
#  8c recheck_showing ..... re-checks cards already on the page (removes any
#                           that are now broken or fail the backup check)
#  8d run_gallery ......... walks one gallery's Rolodex, checks, and posts
#                           (run once for designers, hair, and makeup)
# -----------------------------------------------------------------------------

DESIGNER_BY_NAME = {p["name"]: p for g in GROUPS.values() for p in g["people"]}


# ---- 8a ----------------------------------------------------------------------
def make_post(designer, article=None, image=""):
    role = designer.get("role", "designer")
    details = details_link(designer)
    site = verified_site(designer) or details     # no website -> the details search
    post = {
        "kind": "article" if article else "profile",
        "group": designer.get("group", "designers"),
        "role": role,
        "origin": designer.get("origin", ""),
        "designer": designer["name"],
        "brand": designer["brand"],
        "website": site,
        "details": details,
        "instagram": find_instagram(designer),
        "categories": designer["cats"],
        "image": image,
        "photo_source": "",
        "headline": "", "url": "", "source": "", "published": "",
    }
    if article:
        post.update({
            "headline": article["headline"],
            "url": (fetch_page(article["url"]) or {}).get("url") or article["url"],
            "source": article["source"],
            "published": article["published_iso"],
        })
    return post


def profile_post(designer, used_photos=()):
    photo, source = person_photo(designer, used_photos)
    post = make_post(designer, None, photo)
    post["photo_source"] = source
    return post


# ---- 8b ----------------------------------------------------------------------
def place_in_category(state, cat_key, post, cursor):
    """Puts a post into the next refresh slot of a category. If that designer
    is already shown in this category, their card is replaced in place."""
    slots = state["cats"][cat_key]
    for i, existing in enumerate(slots):
        if existing and existing["designer"] == post["designer"]:
            slots[i] = post
            return cursor
    if cursor < len(slots):
        slots[cursor] = post
        return cursor + 1
    return cursor


# ---- 8c ----------------------------------------------------------------------
def recheck_showing(state):
    """Cards from earlier days are checked again. A card whose article no
    longer passes, or whose photo is broken, is swapped for a checked
    spotlight card of the same designer (never left empty)."""
    if TEST_MODE:
        return
    verdict = {}
    def still_good(post):
        if not post:
            return True
        key = (post.get("url"), post.get("image"))
        if key in verdict:
            return verdict[key]
        designer = DESIGNER_BY_NAME.get(post["designer"])
        ok, reason = True, "still good"
        if designer is None:
            ok, reason = False, "designer no longer on the list"
        elif post["kind"] == "article":
            passed, why, _ = verify_article({"url": post["url"]}, designer)
            if not passed:
                ok, reason = False, why
        if ok and post.get("image") and not check_photo(post["image"])[0]:
            ok, reason = False, "photo " + check_photo(post["image"])[1]
        verdict[key] = ok
        if not ok:
            CHECK_REPORT["rechecked"].append({"designer": post["designer"],
                                              "headline": post.get("headline", ""),
                                              "removed_because": reason})
            log(f"   removed earlier card for {post['designer']}: {reason}")
        return ok

    def fill_missing(post):
        """Fills in data a card is missing: a real website link (instead of a
        search link) and, for spotlight cards, a photo from that website."""
        d = DESIGNER_BY_NAME.get(post["designer"]) if post else None
        if not d:
            return post
        post["origin"] = d.get("origin", "")
        post["details"] = details_link(d)
        post["instagram"] = find_instagram(d)
        site = verified_site(d)
        if site and post.get("website") != site:
            post["website"] = site
            log(f"   filled in website for {d['name']}: {site}")
        elif not site:
            post["website"] = post["details"]
        if not post.get("image"):
            photo, source = person_photo(d)
            if photo:
                post["image"], post["photo_source"] = photo, source
                log(f"   filled in photo for {d['name']}")
        return post

    log("Re-checking cards already on the page…")
    for gkey in GROUPS:
        slots = group_state(state, gkey)["carousel"]
        for i, post in enumerate(slots):
            if not still_good(post):
                d = DESIGNER_BY_NAME.get(post["designer"])
                slots[i] = profile_post(d) if d else None
            else:
                slots[i] = fill_missing(post)
    for key in CATEGORIES:
        for i, post in enumerate(state["cats"][key]):
            if not still_good(post):
                d = DESIGNER_BY_NAME.get(post["designer"])
                state["cats"][key][i] = profile_post(d) if d else None
            else:
                state["cats"][key][i] = fill_missing(post)


# ---- 8d ----------------------------------------------------------------------
def all_shown_photos(state):
    """Every photo currently showing in any gallery (never shown twice)."""
    return {p["image"] for k in GROUPS for p in group_state(state, k)["carousel"]
            if p and p.get("image")}


def run_gallery(state, key, searcher, used_photos):
    """Walks one gallery's Rolodex: starts after yesterday's stopping point,
    checks each person, posts what passes the backup check into slots
    1 -> N (and the category drop-downs for designers), and stops once every
    slot is refreshed or after one full lap."""
    g = GROUPS[key]
    people, n_slots = g["people"], g["slots"]
    gs = group_state(state, key)
    total = len(people)
    start = gs["next"]
    carousel_cursor = 0
    cat_cursor = {k: 0 for k in CATEGORIES} if g["categories"] else {}
    today = now_utc().date().isoformat()
    searched = 0
    log(f"=== {g['label']}: starting at #{start + 1} of {total}: {people[start]['name']} ===")

    def all_slots_refreshed():
        cats_done = all(cat_cursor[k] >= len(state["cats"][k]) for k in cat_cursor)
        return carousel_cursor >= n_slots and cats_done

    while searched < total and not all_slots_refreshed():
        idx = (start + searched) % total
        person = people[idx]
        searched += 1
        log(f"-> #{idx + 1} {person['name']} ({person['brand']})")

        articles = searcher(person)
        new = [a for a in articles if memory_key(a) not in state["posted"]]
        if not articles:
            log("   nothing today — skipping")
        elif not new:
            log("   only articles already posted from the same source — skipping")
        else:
            post = None
            for article in new[:MAX_ARTICLES_PER_DESIGNER]:
                # ---- BACKUP CHECK: article ----
                if TEST_MODE:
                    passed, why, page = True, "test mode", None
                else:
                    passed, why, page = verify_article(article, person)
                if not passed:
                    report(person, article, "rejected", why)
                    continue
                # ---- BACKUP CHECK: photo ----
                if TEST_MODE:
                    photo, note, rej = "", "test mode", []
                else:
                    photo, note, rej = choose_photo(article, person, page, used_photos)
                if not photo and not TEST_MODE:
                    report(person, article, "rejected", "article verified but " + note, "", note, rej)
                    continue
                post = make_post(person, article, photo)
                state["posted"][memory_key(article)] = today
                used_photos.add(photo)
                report(person, article, "posted", why, photo, note, rej)
                break
            if post is None:
                log("   no article passed the backup check — skipping")
            else:
                if carousel_cursor < n_slots:
                    gs["carousel"][carousel_cursor] = post
                    log(f"   {g['label']} slot {carousel_cursor + 1}")
                    carousel_cursor += 1
                for cat in person["cats"]:
                    if cat in cat_cursor:
                        cat_cursor[cat] = place_in_category(state, cat, post, cat_cursor[cat])

        if not TEST_MODE:
            time.sleep(PAUSE_BETWEEN_SEARCHES)

    gs["next"] = (start + searched) % total
    log(f"Done with {g['label']}: searched {searched}, refreshed {carousel_cursor} slots. "
        f"Tomorrow starts at #{gs['next'] + 1}: {people[gs['next']]['name']}")
    return state


def daily_run(state, searcher):
    """Runs all three galleries, one after another."""
    used_photos = all_shown_photos(state)
    for key in GROUPS:
        state = run_gallery(state, key, searcher, used_photos)
    return state


# =============================================================================
#  SECTION 9 — FIRST-RUN FALLBACK: FILL EMPTY SLOTS WITH SPOTLIGHT CARDS
# =============================================================================
#  An empty slot gets a "spotlight" card: the designer, their checked website
#  link and a checked photo from their site. Designers WITH a checked photo
#  are used first. Spotlight cards are replaced as soon as real news arrives.
# -----------------------------------------------------------------------------

def fill_empty_slots(state):
    def best_first(pool):
        if TEST_MODE:
            return sorted(pool, key=lambda d: d["site"] == "")
        return sorted(pool, key=lambda d: (d["site"] == "",))

    used = all_shown_photos(state)
    def spotlight(d):
        post = profile_post(d, used)
        if post["image"]:
            used.add(post["image"])
        return post

    for gkey, g in GROUPS.items():
        slots = group_state(state, gkey)["carousel"]
        if all(slots):
            continue
        shown = {p["designer"] for p in slots if p}
        pool = best_first([d for d in g["people"] if d["name"] not in shown])
        for i, slot in enumerate(slots):
            if slot is None and pool:
                slots[i] = spotlight(pool.pop(0))

    for key in CATEGORIES:
        slots = state["cats"][key]
        if all(slots):
            continue
        shown = {p["designer"] for p in slots if p}
        members = best_first([d for d in DESIGNERS if key in d["cats"] and d["name"] not in shown])
        for i, slot in enumerate(slots):
            if slot is None and members:
                slots[i] = spotlight(members.pop(0))
    return state


# =============================================================================
#  SECTION 10 — WRITING THE FILES (feed for the website + check report)
# =============================================================================

def write_feed(state):
    feed = {
        "updated": now_utc().isoformat(),
        "carousel": [p for p in state["carousel"] if p],
        "categories": [
            {"key": k, "label": label, "posts": [p for p in state["cats"][k] if p]}
            for k, label in CATEGORIES.items()
        ],
        "galleries": [
            {"key": k, "label": g["label"],
             "posts": [p for p in group_state(state, k)["carousel"] if p]}
            for k, g in GROUPS.items() if k != "designers"
        ],
    }
    posted = sum(1 for a in CHECK_REPORT["articles"] if a["result"] == "posted")
    rejected = sum(1 for a in CHECK_REPORT["articles"] if a["result"] == "rejected")
    checks = {
        "date": now_utc().date().isoformat(),
        "summary": f"{posted} posted, {rejected} rejected, "
                   f"{len(CHECK_REPORT['rechecked'])} earlier cards removed",
        **CHECK_REPORT,
    }
    save_json(FEED_FILE, feed)
    save_json(STATE_FILE, state)
    save_json(CHECKS_FILE, checks)
    log(f"Backup check: {checks['summary']}")
    log(f"Wrote {FEED_FILE}, {STATE_FILE} and {CHECKS_FILE}")


# =============================================================================
#  SECTION 11 — OFFLINE TEST MODE  (python scraper/run_daily.py --test)
# =============================================================================
#  Makes up fake news so you can watch the Rolodex logic work without the
#  internet. Internet checks are skipped. Delete data/state.json afterwards.
# -----------------------------------------------------------------------------

def fake_searcher(designer):
    random.seed(designer["name"] + now_utc().date().isoformat())
    if random.random() < 0.45:
        return []
    when = now_utc() - dt.timedelta(hours=random.randint(1, 20))
    return [{
        "headline": {"designer": f"{designer['brand']} unveils a new collection",
                     "hair stylist": f"{designer['name']} creates a red-carpet hair look",
                     "makeup artist": f"{designer['name']} reveals the glam behind a premiere look",
                     }[designer.get("role", "designer")],
        "url": f"https://example.com/{re.sub(r'[^a-z]', '', designer['brand'].lower())}",
        "summary": designer["name"],
        "source": random.choice(["Essence", "Vogue", "WWD", "The Root"]),
        "published_iso": when.isoformat(),
        "feed_image": "",
    }]


# =============================================================================
#  SECTION 12 — START BUTTON
# =============================================================================

if __name__ == "__main__":
    TEST_MODE = "--test" in sys.argv
    state = load_state()
    SITE_STATE = state["sites"]          # same object, so finds are saved
    if TEST_MODE:
        log("TEST MODE — fake news, no internet, checks skipped")
        state = daily_run(state, fake_searcher)
    else:
        recheck_showing(state)
        state = daily_run(state, find_todays_articles)
    state = fill_empty_slots(state)
    write_feed(state)
