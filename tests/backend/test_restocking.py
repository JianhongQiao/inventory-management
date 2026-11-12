"""
Tests for restocking API endpoints.
"""
import pytest


class TestRestockingEndpoints:
    """Test suite for restocking-related endpoints."""

    def test_get_recommendations_structure(self, client):
        """Test getting restock recommendations returns the expected shape."""
        response = client.get("/api/restocking/recommendations?budget=50000")
        assert response.status_code == 200

        data = response.json()
        for field in ["budget", "total_candidates", "funded_count", "excluded_count",
                      "total_shortfall_cost", "funded_cost", "remaining_budget", "items"]:
            assert field in data

        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0

        first_item = data["items"][0]
        required_fields = [
            "sku", "name", "category", "warehouse", "trend", "quantity_on_hand",
            "reorder_point", "forecasted_demand", "shortfall_qty", "unit_cost",
            "line_cost", "lead_time_days", "rank", "funded"
        ]
        for field in required_fields:
            assert field in first_item, f"Missing field: {field}"

    def test_recommendations_respects_budget(self, client):
        """Test that funded items never exceed the given budget."""
        budget = 15000
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        assert response.status_code == 200

        data = response.json()
        funded_total = sum(item["line_cost"] for item in data["items"] if item["funded"])
        assert funded_total <= budget + 0.01
        assert abs(data["funded_cost"] - funded_total) < 0.01

    def test_recommendations_shortfall_math(self, client):
        """Test that shortfall_qty matches forecasted_demand minus quantity_on_hand."""
        response = client.get("/api/restocking/recommendations?budget=100000")
        data = response.json()

        for item in data["items"]:
            expected_shortfall = max(item["forecasted_demand"] - item["quantity_on_hand"], 0)
            assert item["shortfall_qty"] == expected_shortfall
            assert item["shortfall_qty"] > 0  # only candidates with a real shortfall are returned
            expected_line_cost = round(item["shortfall_qty"] * item["unit_cost"], 2)
            assert abs(item["line_cost"] - expected_line_cost) < 0.01

    def test_recommendations_zero_budget_funds_nothing(self, client):
        """Test that a zero budget funds no items."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["funded_count"] == 0
        assert data["funded_cost"] == 0
        for item in data["items"]:
            assert item["funded"] is False

    def test_recommendations_negative_budget_rejected(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restocking/recommendations?budget=-100")
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_recommendations_warehouse_filter_scoping(self, client):
        """Test that recommendations are scoped to the warehouse filter."""
        response = client.get("/api/restocking/recommendations?budget=100000&warehouse=Tokyo")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            assert item["warehouse"] == "Tokyo"

    def test_recommendations_category_filter_scoping(self, client):
        """Test that recommendations are scoped to the category filter."""
        response = client.get("/api/restocking/recommendations?budget=100000&category=Sensors")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            assert item["category"].lower() == "sensors"

    def test_recommendations_ranking_deterministic(self, client):
        """Test that repeated requests with identical params return identical order and lead times."""
        response_1 = client.get("/api/restocking/recommendations?budget=50000")
        response_2 = client.get("/api/restocking/recommendations?budget=50000")

        skus_1 = [item["sku"] for item in response_1.json()["items"]]
        skus_2 = [item["sku"] for item in response_2.json()["items"]]
        assert skus_1 == skus_2

        lead_times_1 = [item["lead_time_days"] for item in response_1.json()["items"]]
        lead_times_2 = [item["lead_time_days"] for item in response_2.json()["items"]]
        assert lead_times_1 == lead_times_2

    def test_create_restocking_order_success(self, client):
        """Test submitting a restocking order with sufficient budget."""
        response = client.post("/api/restocking/orders", json={"budget": 50000})
        assert response.status_code == 201

        order = response.json()
        assert order["source"] == "restocking"
        assert order["order_number"].startswith("RSO-2025-")
        assert isinstance(order["lead_time_days"], int)
        assert order["lead_time_days"] > 0
        assert len(order["items"]) > 0
        assert order["total_value"] > 0

    def test_create_restocking_order_appears_in_orders_list(self, client):
        """Test that a submitted restocking order shows up via GET /api/orders."""
        create_response = client.post("/api/restocking/orders", json={"budget": 20000})
        assert create_response.status_code == 201
        order_number = create_response.json()["order_number"]

        orders_response = client.get("/api/orders")
        assert orders_response.status_code == 200
        order_numbers = [o["order_number"] for o in orders_response.json()]
        assert order_number in order_numbers

    def test_create_restocking_order_insufficient_budget_returns_400(self, client):
        """Test that a budget too small to fund any item returns 400."""
        response = client.post("/api/restocking/orders", json={"budget": 0})
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_restocking_order_negative_budget_rejected(self, client):
        """Test that a negative budget is rejected on submission."""
        response = client.post("/api/restocking/orders", json={"budget": -500})
        assert response.status_code == 400

    def test_create_restocking_order_respects_category_filter(self, client):
        """Test that a submitted order's items all belong to the requested category."""
        response = client.post(
            "/api/restocking/orders",
            json={"budget": 100000, "category": "Actuators"}
        )
        assert response.status_code == 201

        order = response.json()
        inventory_response = client.get("/api/inventory?category=Actuators")
        actuator_skus = {item["sku"] for item in inventory_response.json()}

        for item in order["items"]:
            assert item["sku"] in actuator_skus
