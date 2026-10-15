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
        "Price information",
        ["Any price information", "Price listed only", "Price not listed"],
        index=0,
        help="Only uses price data explicitly tagged in OpenStreetMap; many places may not have it.",
    )
    name_filter = st.text_input("Name contains", placeholder="e.g. toast")
    show_map = st.checkbox("Show map (may load slower)", value=False)
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

places = st.session_state.places
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

        has_price = bool(place.get("price") and str(place["price"]).strip())
        if price_filter == "Price listed only":
            price_match = has_price
        elif price_filter == "Price not listed":
            price_match = not has_price
        else:
            price_match = True

        name_match = not name_filter.strip() or name_filter.strip().lower() in place["name"].lower()
        if category_match and cuisine_match and price_match and name_match:
            filtered.append(place)

    favorites_tab, all_tab = st.tabs([
        f"⭐ Saved ({sum(1 for p in places if p['id'] in st.session_state.favorites)})",
        f"🍽️ Nearby ({len(filtered)})",
    ])

    with all_tab:
        st.caption(f"Area: {st.session_state.last_search_label} · Sorted by distance")
        c1, c2 = st.columns(2)
        c1.metric("Matching places", len(filtered))
        c2.metric("Saved places", sum(1 for p in places if p["id"] in st.session_state.favorites))
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
            st.caption(f"Showing up to {display_limit} results to keep the page responsive.")
            for place in filtered[:display_limit]:
                saved = place["id"] in st.session_state.favorites
                title = f"{'⭐ ' if saved else ''}{place['name']} · {place['distance_km']:.2f} km"
                with st.expander(title, expanded=False):
                    st.write(f"**Food type:** {place['category']}")
                    st.write(f"**Cuisine:** {place['cuisine'] if place['cuisine'] else 'Not listed'}")
                    st.write(f"**Address:** {place['address']}")
                    details = []
                    if place["opening_hours"]:
                        details.append(f"Hours: {place['opening_hours']}")
                    details.append(f"Price range: {place['price'] if place['price'] else 'Not listed'}")
                    if place["phone"]:
                        details.append(f"Phone: {place['phone']}")
                    st.caption(" · ".join(details) if details else "Hours, price and contact details not listed")
                    st.markdown(f"[Open in Google Maps](https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']})")
                    if place["website"]:
                        st.markdown(f"[Website / more information]({place['website']})")
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
                    st.write(f"**Price range:** {place['price'] if place['price'] else 'Not listed'}")
                    st.write(f"**Address:** {place['address']}")
                    st.markdown(f"[Open in Google Maps](https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']})")
                    if st.button("Remove saved place", key=f"remove_{place['id']}"):
                        st.session_state.favorites.remove(place["id"])
                        st.rerun()

    st.divider()
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
        "Location search uses OpenStreetMap's Nominatim service and nearby food discovery uses the Overpass API. "
        "Your typed location is sent to Nominatim to find coordinates. The app does not request your phone GPS. "
        "Community data may be incomplete, and current opening status is not verified. Cuisine and price ranges appear only when explicitly tagged; many places may show 'Not listed'."
    )
    st.write("Favourites currently last for the active Streamlit session. Permanent cross-device storage is a future improvement.")
