import math
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "Lunch Roulette SG"
USER_AGENT = "LunchRouletteSG/0.1 (personal lunch discovery app)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
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
      .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem;}
      .hero {padding: 1.25rem 1.4rem; border-radius: 16px;
             background: linear-gradient(120deg, rgba(14,116,144,.16), rgba(22,163,74,.10));
             border: 1px solid rgba(128,128,128,.25); margin-bottom: 1rem;}
      .muted {opacity: .75; font-size: .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero">
      <h1 style="margin:0;">🍜 {APP_TITLE}</h1>
      <p style="margin:.45rem 0 0 0;">Less scrolling. More lunch. Find food near your office.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption("Prototype • Restaurant data from OpenStreetMap • Works in a mobile browser")

if "places" not in st.session_state:
    st.session_state.places = []
if "favorites" not in st.session_state:
    st.session_state.favorites = set()
if "last_search_label" not in st.session_state:
    st.session_state.last_search_label = ""


@st.cache_data(ttl=60 * 60, show_spinner=False)
def geocode_place(query: str) -> dict[str, Any] | None:
    """Resolve an office name/address to coordinates using Nominatim."""
    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": query + ", Singapore",
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "sg",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    result = results[0]
    return {
        "lat": float(result["lat"]),
        "lon": float(result["lon"]),
        "display_name": result.get("display_name", query),
    }


@st.cache_data(ttl=60 * 30, show_spinner=False)
def discover_places(lat: float, lon: float, radius_m: int) -> list[dict[str, Any]]:
    """Find mapped eateries near a coordinate using the public Overpass API."""
    query = f"""
    [out:json][timeout:25];
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
                timeout=40,
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
                    tags.get("cuisine")
                    or tags.get("amenity")
                    or tags.get("shop")
                    or "food"
                )
                category = category.replace("_", " ").replace(";", ", ")
                address_parts = [
                    tags.get("addr:housenumber"),
                    tags.get("addr:street"),
                    tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
                ]
                address = ", ".join(part for part in address_parts if part) or "Address not listed"
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
                    }
                )
            return places
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Restaurant data service unavailable. Details: {last_error}")


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


with st.sidebar:
    st.header("Find your lunch")
    office_query = st.text_input(
        "Office / MRT / building",
        placeholder="e.g. Raffles Place MRT",
        help="Enter a building, street, MRT station or landmark in Singapore.",
    )
    radius_label = st.selectbox(
        "How far are you willing to go?",
        ["5-minute walk (~400 m)", "10-minute walk (~800 m)", "15-minute walk (~1.2 km)", "20-minute walk (~1.6 km)", "Explore nearby (~3 km)"],
        index=2,
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
    cuisine_filter = st.text_input(
        "Cuisine keyword (optional)",
        placeholder="e.g. Japanese, chicken rice",
    )
    name_filter = st.text_input("Name contains (optional)", placeholder="e.g. kaya toast")
    search_button = st.button("🔎 Find food nearby", type="primary", use_container_width=True)
    st.divider()
    st.caption("Data is community-mapped. Details may be incomplete or outdated.")

if search_button:
    if not office_query.strip():
        st.warning("Enter your office building, street or nearby MRT station first.")
    else:
        try:
            with st.spinner("Finding your location in Singapore…"):
                location = geocode_place(office_query.strip())
            if not location:
                st.error("Couldn't find that location. Try a nearby MRT station or a fuller address.")
            else:
                with st.spinner("Looking for mapped eateries nearby…"):
                    places = discover_places(location["lat"], location["lon"], radius)
                for place in places:
                    place["distance_km"] = distance_km(
                        location["lat"], location["lon"], place["lat"], place["lon"]
                    )
                st.session_state.places = sorted(places, key=lambda p: p["distance_km"])
                st.session_state.office_location = location
                st.session_state.last_search_label = office_query.strip()
                st.session_state.last_radius = radius
        except requests.RequestException:
            st.error("Couldn't reach the location service. Please try again in a moment.")
        except RuntimeError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Something went wrong: {exc}")

places = st.session_state.places

if places:
    office_location = st.session_state.get("office_location")
    filtered = []
    for place in places:
        cat = place["category"].lower()
        selected_cats = {x.lower() for x in category_filter}
        category_match = not selected_cats or any(
            selected in cat or cat in selected for selected in selected_cats
        )
        keyword = cuisine_filter.strip().lower()
        cuisine_match = not keyword or keyword in (
            place["name"] + " " + place["category"] + " " + place["cuisine"]
        ).lower()
        name_match = not name_filter.strip() or name_filter.strip().lower() in place["name"].lower()
        if category_match and cuisine_match and name_match:
            filtered.append(place)

    favorites_tab, all_tab = st.tabs(
        [f"⭐ Favourites ({len(st.session_state.favorites)})", f"🍽️ Nearby food ({len(filtered)})"]
    )

    with all_tab:
        if office_location:
            st.caption(
                f"Search area: {st.session_state.last_search_label} · "
                f"{st.session_state.get('last_radius', radius)} m radius"
            )
        col1, col2, col3 = st.columns(3)
        col1.metric("Places found", len(filtered))
        col2.metric("Saved", sum(1 for p in places if p["id"] in st.session_state.favorites))
        col3.metric("Nearest place", f"{filtered[0]['distance_km']:.1f} km" if filtered else "—")

        if office_location:
            map_data = pd.DataFrame(
                [{"lat": office_location["lat"], "lon": office_location["lon"], "label": "Office"}]
                + [{"lat": p["lat"], "lon": p["lon"], "label": p["name"]} for p in filtered]
            )
            st.map(map_data, latitude="lat", longitude="lon", size=18, color="#0F766E")

        if not filtered:
            st.info("No places match these filters. Try a larger radius or fewer filters.")
        else:
            st.subheader("Places to consider")
            for place in filtered:
                with st.container(border=True):
                    left, right = st.columns([5, 1])
                    with left:
                        st.markdown(f"### {place['name']}")
                        st.caption(
                            f"{place['category']} · {place['distance_km']:.2f} km away"
                            + (f" · {place['cuisine']}" if place["cuisine"] else "")
                        )
                        st.write(f"📍 {place['address']}")
                        details = []
                        if place["opening_hours"]:
                            details.append(f"Hours: {place['opening_hours']}")
                        if place["price"]:
                            details.append(f"Price: {place['price']}")
                        if place["phone"]:
                            details.append(f"Phone: {place['phone']}")
                        st.caption(" · ".join(details) if details else "Hours, price and contact details not listed")
                        if place["website"]:
                            st.markdown(f"[Website / more information]({place['website']})")
                        st.markdown(
                            f"[Open in Google Maps](https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']})"
                        )
                    with right:
                        saved = place["id"] in st.session_state.favorites
                        if st.button("★ Saved" if saved else "☆ Save", key=f"fav_{place['id']}"):
                            if saved:
                                st.session_state.favorites.remove(place["id"])
                            else:
                                st.session_state.favorites.add(place["id"])
                            st.rerun()

    with favorites_tab:
        fav_places = [p for p in places if p["id"] in st.session_state.favorites]
        if not fav_places:
            st.info("Your favourites will appear here after you save a place from the nearby food tab.")
        else:
            for place in fav_places:
                with st.container(border=True):
                    st.markdown(f"### {place['name']}")
                    st.caption(f"{place['category']} · {place['distance_km']:.2f} km away")
                    st.markdown(
                        f"[Open in Google Maps](https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']})"
                    )
                    if st.button("Remove favourite", key=f"remove_{place['id']}"):
                        st.session_state.favorites.remove(place["id"])
                        st.rerun()

    st.divider()
    st.subheader("🎲 Can't decide?")
    if st.button("Pick a random place from these results"):
        import random
        if filtered:
            chosen = random.choice(filtered)
            st.success(f"Today's suggestion: {chosen['name']} — {chosen['distance_km']:.2f} km away")
            st.markdown(
                f"[Get directions in Google Maps](https://www.google.com/maps/search/?api=1&query={chosen['lat']},{chosen['lon']})"
            )
        else:
            st.warning("No places match the current filters.")
else:
    st.info("Enter your office location in the sidebar and select **Find food nearby** to get started.")
    st.markdown("### What this first version can do")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**📍 Nearby search**\n\nSearch around an office, MRT station or building.")
    c2.markdown("**🔎 Filters**\n\nNarrow results by mapped food type or keywords.")
    c3.markdown("**⭐ Save & decide**\n\nKeep favourites during your current app session and pick a random option.")

with st.expander("About the data and privacy"):
    st.write(
        "Location search uses OpenStreetMap's Nominatim service, and nearby food discovery uses the "
        "Overpass API. Your typed office query is sent to Nominatim to find coordinates. The app does "
        "not request your phone's GPS location. Public community data may be incomplete, and this MVP "
        "does not verify that a place is currently open."
    )
    st.write(
        "This prototype keeps favourites in the current Streamlit session. They are not yet stored "
        "permanently; persistent cross-device favourites are planned for the next version."
    )
