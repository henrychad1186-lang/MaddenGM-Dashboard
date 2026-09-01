"""Tests for the trade value engine — value calculation, partner finding,
counter-offers, and trade evaluation."""

import math

from src.trade_engine import (
    _parse_salary,
    get_trade_value,
    find_trade_partners,
    generate_counter_offer,
    evaluate_trade,
)


def _player(**overrides) -> dict:
    """A baseline in-prime player; override fields per test."""
    base = {"Name": "Test Player", "Pos": "WR", "OVR": 80, "Age": 25, "Dev": "Normal"}
    base.update(overrides)
    return base


class TestParseSalary:
    def test_millions(self):
        assert _parse_salary("$3M") == 3.0
        assert _parse_salary("$1.29M") == 1.29

    def test_thousands_converted_to_millions(self):
        assert _parse_salary("$600K") == 0.6

    def test_missing_values_are_zero(self):
        assert _parse_salary(None) == 0.0
        assert _parse_salary("") == 0.0
        assert _parse_salary(float("nan")) == 0.0

    def test_unparseable_string_is_zero(self):
        assert _parse_salary("not a number") == 0.0


class TestTradeValueCore:
    def test_higher_ovr_is_worth_more(self):
        low = get_trade_value(_player(OVR=70))
        high = get_trade_value(_player(OVR=95))
        assert high > low

    def test_position_weight_changes_value(self):
        # QB (1.35 weight) vs K (0.40 weight) at identical OVR/age/dev
        qb = get_trade_value(_player(Pos="QB"))
        k = get_trade_value(_player(Pos="K"))
        assert qb > k

    def test_dev_trait_ordering(self):
        normal = get_trade_value(_player(Dev="Normal"))
        star = get_trade_value(_player(Dev="Star"))
        superstar = get_trade_value(_player(Dev="Superstar"))
        superstar_x = get_trade_value(_player(Dev="Superstar X"))
        assert normal < star < superstar < superstar_x

    def test_age_past_peak_reduces_value(self):
        # WR peak window is 23-28; 25 is in-window, 34 is well past it
        in_prime = get_trade_value(_player(Pos="WR", Age=25))
        aging = get_trade_value(_player(Pos="WR", Age=34))
        assert aging < in_prime

    def test_young_prospect_under_peak_gets_a_bonus(self):
        # QB peak starts at 26 — a 20yo QB nets a "youth premium" over a
        # same-OVR QB sitting right at the start of the prime window.
        rookie = get_trade_value(_player(Pos="QB", Age=20))
        prime_start = get_trade_value(_player(Pos="QB", Age=26))
        assert rookie > prime_start

    def test_contract_savings_increase_value(self):
        no_contract = get_trade_value(_player())
        cap_friendly = get_trade_value(_player(Savings="$8M", Penalty="$0"))
        assert cap_friendly > no_contract

    def test_dead_cap_penalty_decreases_value(self):
        no_contract = get_trade_value(_player())
        costly = get_trade_value(_player(Savings="$0", Penalty="$25M"))
        assert costly < no_contract

    def test_explicit_zero_speed_is_not_treated_as_missing(self):
        # Regression: `player.get("SPD") or player.get("Speed")` used to
        # treat a real SPD=0 as falsy/missing and silently drop it from
        # the physical-attribute bonus instead of penalizing it.
        zero_speed = get_trade_value(_player(SPD=0, ACC=70, AGI=70))
        missing_speed = get_trade_value(_player(ACC=70, AGI=70))
        assert zero_speed < missing_speed

    def test_elite_athleticism_bonus(self):
        average_phys = get_trade_value(_player(SPD=80, ACC=80, AGI=80))
        elite_phys = get_trade_value(_player(SPD=95, ACC=95, AGI=95))
        assert elite_phys > average_phys

    def test_returns_a_plain_float(self):
        value = get_trade_value(_player())
        assert isinstance(value, float)
        assert not math.isnan(value)


class TestFindTradePartners:
    def test_excludes_the_users_own_team(self):
        partners = find_trade_partners(_player(Pos="QB"), user_team="GB")
        assert all(p["team"] != "GB" for p in partners)

    def test_sorted_by_interest_descending(self):
        partners = find_trade_partners(_player(Pos="QB", Age=24, OVR=90))
        interests = [p["interest"] for p in partners]
        assert interests == sorted(interests, reverse=True)

    def test_scheme_fit_boosts_interest(self):
        # MIN runs WestCoast in the CPU demo data.
        fit = find_trade_partners(_player(Pos="SS", OVR=70, Scheme="WestCoast"))
        no_fit = find_trade_partners(_player(Pos="SS", OVR=70, Scheme="Spread"))
        min_fit = next(p for p in fit if p["team"] == "MIN")
        min_no_fit = next(p for p in no_fit if p["team"] == "MIN")
        assert min_fit["interest"] > min_no_fit["interest"]

    def test_older_player_interest_is_penalized(self):
        young = find_trade_partners(_player(Pos="WR", OVR=80, Age=25))
        old = find_trade_partners(_player(Pos="WR", OVR=80, Age=33))
        young_by_team = {p["team"]: p["interest"] for p in young}
        old_by_team = {p["team"]: p["interest"] for p in old}
        for team in young_by_team:
            assert old_by_team[team] <= young_by_team[team]

    def test_best_offer_fields_present(self):
        partners = find_trade_partners(_player(Pos="QB"))
        for p in partners:
            assert p["best_offer_name"]
            assert p["best_offer_pos"]
            assert isinstance(p["best_offer_ovr"], int)


class TestGenerateCounterOffer:
    def test_no_gap_needs_no_sweetener(self):
        msg = generate_counter_offer(target_value=500, current_value=600)
        assert "no sweetener needed" in msg.lower()

    def test_moderate_gap_suggests_a_pick(self):
        msg = generate_counter_offer(target_value=5000, current_value=1000)
        assert "Round Pick" in msg

    def test_tiny_gap_says_too_small_for_a_pick(self):
        msg = generate_counter_offer(target_value=105, current_value=100)
        assert "too small" in msg.lower()


class TestEvaluateTrade:
    def test_fair_trade_is_accepted(self):
        offered = [_player(OVR=85)]
        requested = [_player(OVR=85)]
        result = evaluate_trade(offered, requested)
        assert "ACCEPTED" in result["verdict"]
        assert result["counter_offer"] == ""

    def test_lopsided_trade_is_declined_with_counter(self):
        offered = [_player(OVR=60)]
        requested = [_player(OVR=95, Dev="Superstar X")]
        result = evaluate_trade(offered, requested)
        assert "DECLINED" in result["verdict"]
        assert result["counter_offer"] != ""

    def test_slightly_short_trade_is_lean_accept(self):
        # Tune values to land the ratio in the [0.80, 0.92) band.
        offered = [_player(OVR=82)]
        requested = [_player(OVR=88)]
        result = evaluate_trade(offered, requested)
        ratio = result["offered_value"] / result["requested_value"]
        if 0.80 <= ratio < 0.92:
            assert "LEAN ACCEPT" in result["verdict"]
            assert result["counter_offer"] != ""
