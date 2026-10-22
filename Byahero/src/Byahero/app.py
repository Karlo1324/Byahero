"""
ByaHero - Commute Prediction App (Toga / Android)

A native mobile shell for the ByaHero commute predictor. It talks to the same
Flask API the web app uses, so both stay in sync.

Set the API base URL with the BYAHERO_API env var, e.g.
    BYAHERO_API=http://10.0.2.2:3000
(10.0.2.2 is how the Android emulator reaches the host machine.)
"""

import os
import json
import urllib.request
import urllib.error

import toga
from toga.style.pack import pack, COLUMN


DEFAULT_API = "http://10.0.2.2:3000"


class ApiError(Exception):
    """Raised when the API cannot be reached or returns an error."""


class ByaHeroApi:
    """Thin client for the ByaHero Flask API."""

    def __init__(self, base_url=None):
        self.base_url = (base_url or os.environ.get("BYAHERO_API")
                         or DEFAULT_API).rstrip("/")

    def _request(self, path, payload=None, method=None):
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ApiError(f"Server returned {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(
                f"Could not reach the server at {self.base_url}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ApiError("Server sent an unreadable response") from exc

    def get_locations(self, route_id):
        return self._request(f"/api/get-locations?route_id={route_id}")

    def get_stops_after(self, route_id, stop_id):
        return self._request(
            f"/api/get-stops-after?route_id={route_id}&stop_id={stop_id}"
        )

    def predict(self, payload):
        return self._request("/api/predict", payload, method="POST")


class Byahero(toga.App):
    # The routes the app can plan a trip on.
    ROUTES = {1: "Kapatagan to Digos"}

    def startup(self):
        """Construct and show the Toga application."""
        self.api = ByaHeroApi()
        self.locations = []

        main_box = toga.Box(style=pack(COLUMN, padding=12))

        main_box.add(
            toga.Label("ByaHero", style=pack(padding_bottom=2))
        )
        main_box.add(
            toga.Label(
                "Bus Commute Prediction",
                style=pack(padding_bottom=12),
            )
        )

        # --- Route ---
        self.route_select = toga.Selection(
            items=list(self.ROUTES.values()),
            on_change=self.on_route_change,
        )
        main_box.add(toga.Label("Route", style=pack(padding_bottom=2)))
        main_box.add(self.route_select)
        main_box.add(toga.Separator(style=pack(padding=8)))

        # --- Origin ---
        self.origin_select = toga.Selection(
            items=[], on_change=self.on_origin_change
        )
        main_box.add(toga.Label("From (Origin)", style=pack(padding_bottom=2)))
        main_box.add(self.origin_select)
        main_box.add(toga.Separator(style=pack(padding=8)))

        # --- Destination ---
        self.destination_select = toga.Selection(items=[])
        main_box.add(toga.Label("To (Destination)", style=pack(padding_bottom=2)))
        main_box.add(self.destination_select)
        main_box.add(toga.Separator(style=pack(padding=8)))

        # --- Time / day / crowd ---
        self.time_select = toga.Selection(
            items=[
                "6:00 AM", "7:00 AM", "8:00 AM", "9:00 AM", "10:00 AM",
                "11:00 AM", "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM",
                "4:00 PM", "5:00 PM", "6:00 PM", "7:00 PM", "8:00 PM",
            ]
        )
        main_box.add(toga.Label("Time of Day", style=pack(padding_bottom=2)))
        main_box.add(self.time_select)
        main_box.add(toga.Separator(style=pack(padding=8)))

        self.day_select = toga.Selection(
            items=[
                "Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday",
            ]
        )
        main_box.add(toga.Label("Day", style=pack(padding_bottom=2)))
        main_box.add(self.day_select)
        main_box.add(toga.Separator(style=pack(padding=8)))

        self.crowd_select = toga.Selection(
            items=["Low", "Medium", "High"], on_change=self.on_crowd_change
        )
        main_box.add(toga.Label("Crowd Level", style=pack(padding_bottom=2)))
        main_box.add(self.crowd_select)
        main_box.add(toga.Separator(style=pack(padding=8)))

        # --- Action and results ---
        self.predict_button = toga.Button(
            "Get Prediction",
            on_press=self.on_predict,
            style=pack(padding_bottom=8),
        )
        main_box.add(self.predict_button)

        self.result_label = toga.Label("", style=pack(padding_bottom=4))
        main_box.add(self.result_label)

        self.detail_label = toga.Label("", style=pack(padding_bottom=4))
        main_box.add(self.detail_label)

        self.status_label = toga.Label("")
        main_box.add(self.status_label)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = toga.ScrollableContainer(main_box)
        self.main_window.show()

        self.load_locations()

    # ============ EVENT HANDLERS ============

    def on_crowd_change(self, widget=None, **kwargs):
        # Read straight from the widget; the selection is the crowd level.
        pass

    def on_route_change(self, widget=None, **kwargs):
        self.load_locations()

    def on_origin_change(self, widget=None, **kwargs):
        self.load_destinations()

    def load_locations(self):
        """Load the stops for the selected route into the origin picker."""
        route_id = self.current_route_id()
        if route_id is None:
            return
        try:
            data = self.api.get_locations(route_id)
        except ApiError as exc:
            self.set_status(str(exc), error=True)
            return

        self.locations = data.get("locations", [])
        self.origin_select.items = [loc["name"] for loc in self.locations]
        self.destination_select.items = []
        self.set_status("")

    def load_destinations(self):
        """Load the stops that come after the selected origin."""
        route_id = self.current_route_id()
        origin = self.selected_location()
        if route_id is None or origin is None:
            self.destination_select.items = []
            return

        try:
            data = self.api.get_stops_after(route_id, origin["location_id"])
        except ApiError as exc:
            self.set_status(str(exc), error=True)
            return

        self.destination_select.items = [s["name"] for s in data.get("stops", [])]

    def current_route_id(self):
        """The route id matching the current selection, or None."""
        selected = self.route_select.value
        for route_id, name in self.ROUTES.items():
            if name == selected:
                return route_id
        return None

    def selected_location(self):
        """The location record for the selected origin, or None."""
        selected = self.origin_select.value
        for loc in self.locations:
            if loc["name"] == selected:
                return loc
        return None

    def on_predict(self, widget=None, **kwargs):
        route_id = self.current_route_id()
        if route_id is None:
            self.set_status("Choose a route first", error=True)
            return

        origin = self.selected_location()
        if origin is None:
            self.set_status("Choose an origin first", error=True)
            return

        destination = self.destination_select.value
        payload = {
            "route": route_id,
            "origin": origin["location_id"],
            "stop": destination or origin["name"],
            "time": self.time_select.value,
            "day": self.day_select.value,
            "crowd": self.crowd_select.value,
        }

        self.predict_button.enabled = False
        self.set_status("Calculating...")
        try:
            result = self.api.predict(payload)
        except ApiError as exc:
            self.set_status(str(exc), error=True)
            return
        finally:
            self.predict_button.enabled = True

        if not result.get("success"):
            self.set_status(result.get("error", "Prediction failed"), error=True)
            return

        travel_time = result.get("travel_time")
        decision = result.get("decision")
        action = "Leave Now" if decision == "leave_now" else "You Can Wait"

        self.result_label.text = f"{travel_time} minutes - {action}"
        origin_name = result.get("origin") or origin["name"]
        if destination:
            self.detail_label.text = f"From {origin_name} to {destination}"
        else:
            self.detail_label.text = f"From {origin_name}"
        self.set_status("")

    def set_status(self, message, error=False):
        self.status_label.text = message
        self.status_label.style.color = "#DC3545" if error else "#5C6470"


def main():
    return Byahero()
