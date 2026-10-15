import math
import re
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "Lunch Roulette SG"
USER_AGENT = "LunchRouletteSG/0.1 (personal lunch discovery app)"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🍜",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1100px;}
      [data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.18);}
      .hero {
        padding: 1.35rem 1.4rem; border-radius: 20px;
        background: linear-gradient(125deg, #102a2a 0%, #164e45 48%, #1d7664 100%);
        color: white; margin-bottom: .8rem;
        box-shadow: 0 8px 24px rgba(10, 70, 60, .14);
      }
      .hero h1 {font-size: clamp(1.8rem, 5vw, 2.5rem); letter-spacing: -.04em;}
      .hero p {color: rgba(255,255,255,.84); font-size: 1rem;}
      div[data-testid="stMetric"] {
        background: rgba(128,128,128,.06); border: 1px solid rgba(128,128,128,.16);
        padding: .8rem 1rem; border-radius: 14px;
      }
      div[data-testid="stMetricLabel"] {font-size: .85rem;}
      div[data-testid="stExpander"] {
        border: 1px solid rgba(128,128,128,.23); border-radius: 14px;
        overflow: hidden; margin-bottom: .5rem;
      }
      div.stButton > button {border-radius: 12px; min-height: 2.7rem;}
      div.stButton > button[kind="primary"] {
        background: #176b5b; border-color: #176b5b; color: white;
      }
      a {text-underline-offset: 3px;}
      .small-note {opacity: .72; font-size: .85rem;}
      @media (max-width: 640px) {
        .block-container {padding-left: .85rem; padding-right: .85rem;}
        .hero {padding: 1.05rem 1rem; border-radius: 16px;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero">
      <h1 style="margin:0;">🍜 {APP_TITLE}</h1>
      <p style="margin:.45rem 0 0 0;">Good food, less decision fatigue.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption("YOUR OFFICE LUNCH COMPANION  ·  Singapore")

if "places" not in st.session_state:
    st.session_state.places = []
if "favorites" not in st.session_state:
    st.session_state.favorites = set()
if "last_search_label" not in st.session_state:
    st.session_state.last_search_label = ""


@st.cache_data(ttl=60 * 60, show_spinner=False)
def geocode_place(query: str) -> dict[str, Any] | None:
    """Resolve a Singapore office/building/MRT query using OneMap's search API."""
    response = requests.get(
        ONEMAP_SEARCH_URL,
        params={
            "searchVal": query,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results", [])
    if not results:
        return None
    result = results[0]
    lat = result.get("LATITUDE")
    lon = result.get("LONGITUDE")
    if not lat or not lon:
        return None
    return {
        "lat": float(lat),
        "lon": float(lon),
        "display_name": result.get("ADDRESS", query),
    }


@st.cache_data(ttl=60 * 30, show_spinner=False)
def discover_places(lat: float, lon: float, radius_m: int) -> list[dict[str, Any]]:
    """Find mapped eateries near a coordinate using the public Overpass API."""
    query = f"""
    [out:json][timeout:18];
    (
      nwr(around:{radius_m},{lat},{lon})["amenity"~"^(restaurant|cafe|fast_food|food_court|ice_cream|pub|bar)$"];
      nwr(around:{radius_m},{lat},{lon})["shop"~"^(bakery|confectionery|deli|pastry)$"];
    );
    out center tags;
    """
    last_error = None
    for endpoint in OVERPASS_URLS:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=25,
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])
            places = []
            seen = set()
            for item in elements:
                tags = item.get("tags", {})
                name = tags.get("name") or tags.get("brand") or tags.get("operator")
                if not name:
                    continue
                if "lat" in item and "lon" in item:
                    p_lat, p_lon = float(item["lat"]), float(item["lon"])
                elif "center" in item:
                    p_lat = float(item["center"]["lat"])
                    p_lon = float(item["center"]["lon"])
                else:
                    continue

                osm_type = item.get("type", "node")
                osm_id = item.get("id")
                unique_key = f"{osm_type}/{osm_id}"
                if unique_key in seen:
                    continue
                seen.add(unique_key)

                category = (
                    tags.get("amenity")
                    or tags.get("shop")
                    or "food"
                )
                category = category.replace("_", " ").replace(";", ", ")
                # OSM address fields are inconsistent; use all useful available components.
                address_parts = [
                    tags.get("addr:housenumber"),
                    tags.get("addr:street"),
                    tags.get("addr:building") or tags.get("building"),
                    tags.get("addr:unit"),
                    tags.get("addr:level"),
                    tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
                    tags.get("addr:postcode"),
                ]
                address = ", ".join(dict.fromkeys(part for part in address_parts if part)) or "Address not listed"
                website = tags.get("website") or tags.get("contact:website")
                phone = tags.get("phone") or tags.get("contact:phone")
                opening_hours = tags.get("opening_hours")
                price = tags.get("price_range") or tags.get("price")

                places.append(
                    {
                        "id": unique_key,
                        "name": name,
                        "category": category.title(),
                        "lat": p_lat,
                        "lon": p_lon,
                        "address": address,
                        "website": website,
                        "phone": phone,
                        "opening_hours": opening_hours,
                        "price": price,
                        "cuisine": tags.get("cuisine", "").replace("_", ", ").title(),
                        "brand": tags.get("brand", ""),
                        "diet": tags.get("diet", ""),
                        "outdoor_seating": tags.get("outdoor_seating", ""),
                        "takeaway": tags.get("takeaway", ""),
                        "osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                    }
                )
            return places
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Restaurant data service unavailable. Details: {last_error}")


OVERRIDE_COLUMNS = [
    "id", "name", "address_override", "cuisine_override", "budget_band",
    "personal_rating", "notes", "website_override", "opening_hours_override"
]
BUDGET_BANDS = ["Unknown", "Under S$10", "S$10–20", "S$21–40", "Over S$40"]


def normalize_overrides(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep only supported override fields and normalize blank values."""
    for column in OVERRIDE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[OVERRIDE_COLUMNS].fillna("")
    frame["id"] = frame["id"].astype(str)
    return frame.drop_duplicates(subset=["id"], keep="last")


def apply_overrides(places: list[dict[str, Any]], overrides: pd.DataFrame) -> list[dict[str, Any]]:
    """Apply user-maintained corrections without presenting them as official data."""
    lookup = {
        str(row["id"]): row
        for _, row in normalize_overrides(overrides).iterrows()
        if str(row.get("id", "")).strip()
    }
    for place in places:
        row = lookup.get(str(place["id"]))
        place["personal_rating"] = ""
        place["notes"] = ""
        place["budget_band"] = price_band(place.get("price"))
        place["data_source_note"] = "OpenStreetMap"
        if row is None:
            continue
        for field, target in [
            ("address_override", "address"),
            ("cuisine_override", "cuisine"),
            ("website_override", "website"),
            ("opening_hours_override", "opening_hours"),
        ]:
            value = str(row.get(field, "")).strip()
            if value:
                place[target] = value
        budget = str(row.get("budget_band", "")).strip()
        if budget and budget in BUDGET_BANDS:
            place["budget_band"] = budget
            place["data_source_note"] = "OpenStreetMap + your correction"
        place["personal_rating"] = str(row.get("personal_rating", "")).strip()
        place["notes"] = str(row.get("notes", "")).strip()
    return places


if "overrides" not in st.session_state:
    st.session_state.overrides = pd.DataFrame(columns=OVERRIDE_COLUMNS)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def clean_text(value: Any, fallback: str = "Not listed") -> str:
    if value is None or str(value).strip() == "":
        return fallback
    return str(value)


def price_band(value: Any) -> str:
    """Classify only explicit numeric price tags; never guess missing prices."""
    if value is None or str(value).strip() == "":
        return "Unknown"
    raw = str(value).strip().lower()
    # Only create SGD budget bands when the source explicitly identifies SGD.
    # Generic numbers or "$" can mean different currencies or price scales.
    if "sgd" not in raw and "s$" not in raw:
        return "Listed (unclassified)"
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not numbers:
        return "Listed (unclassified)"
    amount = max(numbers)
    if amount < 10:
        return "Under S$10"
    if amount <= 20:
        return "S$10–20"
    if amount <= 40:
        return "S$21–40"
    return "Over S$40"


with st.sidebar:
    st.header("Find your lunch")
    office_query = st.text_input(
        "Office / MRT / building",
        placeholder="e.g. Raffles Place MRT",
        help="Enter a building, street or MRT station in Singapore.",
    )
    radius_label = st.selectbox(
        "Search radius",
        ["5-minute walk (~400 m)", "10-minute walk (~800 m)", "15-minute walk (~1.2 km)", "20-minute walk (~1.6 km)", "Explore nearby (~3 km)"],
        index=1,
    )
    radius_map = {
        "5-minute walk (~400 m)": 400,
        "10-minute walk (~800 m)": 800,
        "15-minute walk (~1.2 km)": 1200,
        "20-minute walk (~1.6 km)": 1600,
        "Explore nearby (~3 km)": 3000,
    }
    radius = radius_map[radius_label]
    category_filter = st.multiselect(
        "Food type",
        ["Restaurant", "Cafe", "Fast Food", "Food Court", "Bakery", "Ice Cream", "Pub", "Bar"],
        default=["Restaurant", "Cafe", "Fast Food", "Food Court", "Bakery"],
    )
    # Cuisine choices are populated from mapped details in the current search.
    discovered_cuisines = sorted({
        item.strip()
        for place in st.session_state.places
        for item in place.get("cuisine", "").split(",")
        if item.strip()
    })
    cuisine_filter = st.multiselect(
        "Cuisine type",
        discovered_cuisines,
        default=[],
        help="Options depend on cuisine information available in OpenStreetMap.",
    )
    price_filter = st.selectbox(
        "Budget",
        ["Any budget", "Under S$10", "S$10–20", "S$21–40", "Over S$40", "Price listed (currency unclear)", "Price not listed"],
        index=0,
        help="Budget bands are assigned only when OpenStreetMap has a numeric price tag. Missing prices are not guessed.",
    )
    name_filter = st.text_input("Name contains", placeholder="e.g. toast")
    show_map = st.checkbox("Show map (may load slower)", value=False)
    st.divider()
    st.subheader("Your saved corrections")
    uploaded_overrides = st.file_uploader(
        "Load your corrections CSV",
        type=["csv"],
        help="Upload a corrections CSV you previously exported to restore your own cuisine, budget and notes.",
    )
    if uploaded_overrides is not None:
        try:
            loaded = pd.read_csv(uploaded_overrides, dtype=str).fillna("")
            st.session_state.overrides = normalize_overrides(loaded)
            st.success(f"Loaded {len(st.session_state.overrides)} saved corrections.")
        except Exception:
            st.error("Could not read that CSV. Use a corrections file exported by this app.")
    search_button = st.button("🔎 Find food nearby", type="primary", use_container_width=True)
    st.divider()
    st.caption("OpenStreetMap data can be incomplete. Search results are cached to reduce repeat requests.")

if search_button:
    if not office_query.strip():
        st.warning("Enter your office building, street or nearby MRT station first.")
    else:
        try:
            with st.spinner("Finding your location…"):
                location = geocode_place(office_query.strip())
            if not location:
                st.error("Couldn't find that location. Try a nearby MRT station or a fuller address.")
            else:
                with st.spinner("Searching for nearby food… this can take a little while on the first search."):
                    places = discover_places(location["lat"], location["lon"], radius)
                for place in places:
                    place["distance_km"] = distance_km(
                        location["lat"], location["lon"], place["lat"], place["lon"]
                    )
                places = apply_overrides(places, st.session_state.overrides)
                st.session_state.places = sorted(places, key=lambda p: p["distance_km"])
                st.session_state.office_location = location
                st.session_state.last_search_label = office_query.strip()
                st.session_state.last_radius = radius
        except requests.RequestException:
            st.error("The location service is busy or unavailable. Please try again shortly.")
        except RuntimeError:
            st.error("The restaurant data service is busy. Try a smaller radius or retry in a minute.")
        except Exception as exc:
            st.error(f"Something went wrong: {exc}")

places = apply_overrides(st.session_state.places, st.session_state.overrides) if st.session_state.places else []
st.session_state.places = places
if places:
    office_location = st.session_state.get("office_location")
    filtered = []
    selected_cats = {x.lower() for x in category_filter}
    for place in places:
        cat = place["category"].lower()
        category_match = not selected_cats or any(selected in cat or cat in selected for selected in selected_cats)
        place_cuisines = {
            item.strip().lower()
            for item in place.get("cuisine", "").split(",")
            if item.strip()
        }
        selected_cuisines = {item.lower() for item in cuisine_filter}
        cuisine_match = not selected_cuisines or bool(place_cuisines & selected_cuisines)

        band = place.get("budget_band") or price_band(place.get("price"))
        if price_filter == "Any budget":
            price_match = True
        elif price_filter == "Price not listed":
            price_match = band == "Unknown"
        elif price_filter == "Price listed (currency unclear)":
            price_match = band == "Listed (unclassified)"
        else:
            price_match = band == price_filter

        name_match = not name_filter.strip() or name_filter.strip().lower() in place["name"].lower()
        if category_match and cuisine_match and price_match and name_match:
            filtered.append(place)

    favorites_tab, all_tab = st.tabs([
        f"⭐ Saved ({sum(1 for p in places if p['id'] in st.session_state.favorites)})",
        f"🍽️ Nearby ({len(filtered)})",
    ])

    with all_tab:
        st.caption(f"Area: {st.session_state.last_search_label} · Sorted by distance")
        c1, c2, c3 = st.columns(3)
        c1.metric("Matches", len(filtered))
        c2.metric("Saved", sum(1 for p in places if p["id"] in st.session_state.favorites))
        c3.metric("Search radius", f"{st.session_state.get('last_radius', radius)} m")
        if show_map and office_location:
            with st.expander("Map view", expanded=True):
                map_places = filtered[:40]
                map_data = pd.DataFrame(
                    [{"lat": office_location["lat"], "lon": office_location["lon"]}]
                    + [{"lat": p["lat"], "lon": p["lon"]} for p in map_places]
                )
                st.map(map_data, latitude="lat", longitude="lon", size=16)
        if not filtered:
            st.info("No places match. Try fewer filters or a larger radius.")
        else:
            # Render a capped list to keep mobile scrolling and Streamlit reruns light.
            display_limit = 30
            st.caption(f"NEARBY PICKS  ·  Showing up to {display_limit} places for a smoother mobile experience.")
            for place in filtered[:display_limit]:
                saved = place["id"] in st.session_state.favorites
                title = f"{'⭐ ' if saved else ''}{place['name']} · {place['distance_km']:.2f} km"
                with st.expander(title, expanded=False):
                    st.write(f"**Food type:** {place['category']}")
                    st.write(f"**Cuisine:** {place['cuisine'] if place['cuisine'] else 'Not listed'}")
                    st.write(f"**Address:** {place['address']}")
                    st.write(f"**Budget:** {place.get('budget_band', price_band(place.get('price')))}")
                    if place.get("personal_rating"):
                        st.write(f"**Your rating:** {place['personal_rating']}/5")
                    if place.get("notes"):
                        st.caption(f"Your note: {place['notes']}")
                    details = []
                    if place["opening_hours"]:
                        details.append(f"Hours: {place['opening_hours']}")
                    if place["price"]:
                        details.append(f"OSM price tag: {place['price']}")
                    if place.get("brand"):
                        details.append(f"Brand: {place['brand']}")
                    if place.get("takeaway"):
                        details.append(f"Takeaway: {place['takeaway']}")
                    if place.get("outdoor_seating"):
                        details.append(f"Outdoor seating: {place['outdoor_seating']}")
                    if place["phone"]:
                        details.append(f"Phone: {place['phone']}")
                    st.caption(" · ".join(details) if details else "Hours, price and contact details not listed")
                    st.markdown(f"[Open in Google Maps](https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']})")
                    if place["website"]:
                        st.markdown(f"[Website / more information]({place['website']})")
                    with st.form(key=f"edit_{place['id']}"):
                        st.caption("Improve this entry for your own future searches")
                        edit_address = st.text_input("Corrected address", value="" if place["address"] == "Address not listed" else place["address"], key=f"addr_{place['id']}")
                        edit_cuisine = st.text_input("Cuisine", value=place["cuisine"], key=f"cuisine_{place['id']}", placeholder="e.g. Japanese, ramen")
                        current_budget = place.get("budget_band", "Unknown")
                        budget_options = BUDGET_BANDS
                        edit_budget = st.selectbox("Budget band (your estimate)", budget_options, index=budget_options.index(current_budget) if current_budget in budget_options else 0, key=f"budget_{place['id']}")
                        edit_rating = st.selectbox("Your personal rating", ["", "1", "2", "3", "4", "5"], index=["", "1", "2", "3", "4", "5"].index(place.get("personal_rating", "")) if place.get("personal_rating", "") in ["", "1", "2", "3", "4", "5"] else 0, key=f"rating_{place['id']}")
                        edit_notes = st.text_input("Your notes", value=place.get("notes", ""), key=f"notes_{place['id']}", placeholder="e.g. try the laksa")
                        edit_website = st.text_input("Website (optional)", value=place["website"], key=f"website_{place['id']}")
                        edit_hours = st.text_input("Opening hours (optional)", value=place["opening_hours"], key=f"hours_{place['id']}")
                        if st.form_submit_button("Save my corrections"):
                            current = normalize_overrides(st.session_state.overrides)
                            existing = current[current["id"] != str(place["id"])]
                            new_row = pd.DataFrame([{
                                "id": str(place["id"]), "name": place["name"],
                                "address_override": edit_address, "cuisine_override": edit_cuisine,
                                "budget_band": edit_budget, "personal_rating": edit_rating,
                                "notes": edit_notes, "website_override": edit_website,
                                "opening_hours_override": edit_hours,
                            }])
                            st.session_state.overrides = normalize_overrides(pd.concat([existing, new_row], ignore_index=True))
                            st.session_state.places = apply_overrides(st.session_state.places, st.session_state.overrides)
                            st.success("Your correction is saved for this session. Export the CSV below to keep it.")
                            st.rerun()
                    if st.button("Remove from saved" if saved else "☆ Save place", key=f"fav_{place['id']}"):
                        if saved:
                            st.session_state.favorites.remove(place["id"])
                        else:
                            st.session_state.favorites.add(place["id"])
                        st.rerun()
            if len(filtered) > display_limit:
                st.info(f"{len(filtered) - display_limit} more places are hidden. Narrow your search or choose a smaller radius.")

    with favorites_tab:
        fav_places = [p for p in places if p["id"] in st.session_state.favorites]
        if not fav_places:
            st.info("Save a place from Nearby and it will appear here for this session.")
        else:
            for place in fav_places:
                with st.expander(f"⭐ {place['name']} · {place['distance_km']:.2f} km", expanded=False):
                    st.write(f"**Food type:** {place['category']} · **Cuisine:** {place['cuisine'] if place['cuisine'] else 'Not listed'}")
                    st.write(f"**Budget:** {price_band(place['price'])}")
                    if place["price"]:
                        st.caption(f"Source price tag: {place['price']}")
                    st.write(f"**Address:** {place['address']}")
                    st.markdown(f"[Open in Google Maps](https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']})")
                    if st.button("Remove saved place", key=f"remove_{place['id']}"):
                        st.session_state.favorites.remove(place["id"])
                        st.rerun()

    st.divider()
    st.subheader("Keep your restaurant corrections")
    st.caption("Streamlit Community Cloud may reset local files, so export this CSV and upload it next time. Personal budget bands and ratings are your own notes, not official restaurant data.")
    export_frame = normalize_overrides(st.session_state.overrides)
    st.download_button(
        "⬇️ Export corrections CSV",
        data=export_frame.to_csv(index=False).encode("utf-8"),
        file_name="lunch_roulette_corrections.csv",
        mime="text/csv",
        use_container_width=True,
    )
    if st.button("🎲 Pick a random lunch", use_container_width=True):
        import random
        if filtered:
            chosen = random.choice(filtered)
            st.session_state.random_pick = chosen["id"]
        else:
            st.warning("No places match the current filters.")
    if st.session_state.get("random_pick"):
        chosen = next((p for p in places if p["id"] == st.session_state.random_pick), None)
        if chosen:
            st.success(f"Lunch suggestion: {chosen['name']} · {chosen['distance_km']:.2f} km away")
            st.markdown(f"[Get directions in Google Maps](https://www.google.com/maps/search/?api=1&query={chosen['lat']},{chosen['lon']})")
else:
    st.info("Enter your office location in the sidebar and tap **Find food nearby** to get started.")
    st.markdown("### Built for quick lunch decisions")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**📍 Nearby search**\n\nSearch around your office or MRT station.")
    c2.markdown("**🔎 Cuisine & price filters**\n\nNarrow results by cuisine and available price information.")
    c3.markdown("**🎲 Random lunch**\n\nLet the app choose from your results.")

with st.expander("About the data and privacy"):
    st.write(
        "Nearby places and mapped details come from OpenStreetMap contributors (© OpenStreetMap contributors, ODbL). "
        "The app uses Nominatim for user-initiated office-location lookup and Overpass for nearby mapped eateries; "
        "public endpoints are best-effort, have usage limits, and can be temporarily unavailable. Requests are cached. "
        "The app does not request your phone GPS."
    )
    st.write(
        "OpenStreetMap does not guarantee complete cuisine, price, ratings, phone, address or opening-hour details. "
        "This free-only version does not fabricate public ratings or prices. You can add personal cuisine corrections, "
        "budget estimates, ratings, notes and address/hour/website corrections, then export them to CSV and upload them "
        "again later. Those edits are personal annotations, not verified public facts."
    )
    st.markdown("[OpenStreetMap data and licence](https://www.openstreetmap.org/copyright) · [OneMap API terms](https://www.onemap.gov.sg/legal/apitermsofservice.html)")
