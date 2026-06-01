"""Tests for seed.contracts — SPEC-007, INTF-001 through INTF-005."""


from organvm_engine.seed.contracts import (
    CANONICAL_SIGNAL_TYPES,
    check_promotion_contract_monotonicity,
    check_signal_compatibility,
    validate_contract,
)

# ---------------------------------------------------------------------------
# validate_contract — well-formed edges
# ---------------------------------------------------------------------------

class TestValidateContract:
    def test_valid_seed(self):
        seed = {
            "produces": [
                {"type": "theory", "description": "frameworks", "consumers": ["ORGAN-II"]},
            ],
            "consumes": [
                {"type": "governance_event", "source": "ORGAN-IV"},
            ],
        }
        valid, errors = validate_contract(seed)
        assert valid
        assert errors == []

    def test_empty_edges(self):
        seed = {"produces": [], "consumes": []}
        valid, errors = validate_contract(seed)
        assert valid
        assert errors == []

    def test_no_edges_at_all(self):
        seed = {"repo": "test"}
        valid, errors = validate_contract(seed)
        assert not valid
        assert "missing required field 'produces'" in errors
        assert "missing required field 'consumes'" in errors

    def test_bare_string_produces(self):
        seed = {"produces": ["theory"], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("bare string" in e for e in errors)

    def test_bare_string_consumes(self):
        seed = {"produces": [], "consumes": ["data"]}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("bare string" in e for e in errors)

    def test_missing_type_field(self):
        seed = {"produces": [{"description": "no type"}], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("missing required field 'type'" in e for e in errors)

    def test_empty_type_field(self):
        seed = {"produces": [{"type": ""}], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("must not be empty" in e for e in errors)

    def test_whitespace_type_field(self):
        seed = {"produces": [{"type": "   "}], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("must not be empty" in e for e in errors)

    def test_non_string_type(self):
        seed = {"produces": [{"type": 42}], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("must be a string" in e for e in errors)

    def test_non_dict_entry(self):
        seed = {"produces": [42], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("expected dict" in e for e in errors)

    def test_non_string_source(self):
        seed = {"produces": [], "consumes": [{"type": "data", "source": 123}]}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("'source' must be a string" in e for e in errors)

    def test_non_list_consumers(self):
        seed = {"produces": [{"type": "theory", "consumers": "ORGAN-II"}], "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("'consumers' must be a list" in e for e in errors)

    def test_produces_not_a_list(self):
        seed = {"produces": "not a list", "consumes": []}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("'produces' must be a list" in e for e in errors)

    def test_consumes_not_a_list(self):
        seed = {"produces": [], "consumes": {"type": "data"}}
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("'consumes' must be a list" in e for e in errors)

    def test_duplicate_produces_type(self):
        seed = {
            "produces": [
                {"type": "theory"},
                {"type": "theory"},
            ],
            "consumes": [],
        }
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("duplicate type 'theory'" in e for e in errors)

    def test_duplicate_consumes_type_and_source(self):
        seed = {
            "produces": [],
            "consumes": [
                {"type": "data", "source": "ORGAN-I"},
                {"type": "data", "source": "ORGAN-I"},
            ],
        }
        valid, errors = validate_contract(seed)
        assert not valid
        assert any("duplicate entry" in e for e in errors)

    def test_same_type_different_source_ok(self):
        seed = {
            "produces": [],
            "consumes": [
                {"type": "data", "source": "ORGAN-I"},
                {"type": "data", "source": "ORGAN-II"},
            ],
        }
        valid, errors = validate_contract(seed)
        assert valid
        assert errors == []

    def test_multiple_errors_collected(self):
        seed = {
            "produces": [
                {"type": 42},
                {"description": "no type"},
            ],
            "consumes": [
                {"type": "data", "source": 99},
            ],
        }
        valid, errors = validate_contract(seed)
        assert not valid
        assert len(errors) >= 3


# ---------------------------------------------------------------------------
# check_signal_compatibility
# ---------------------------------------------------------------------------

class TestSignalCompatibility:
    def test_fully_compatible(self):
        producers = [{"type": "theory"}, {"type": "data"}]
        consumers = [{"type": "theory"}]
        mismatches = check_signal_compatibility(producers, consumers)
        assert mismatches == []

    def test_missing_producer(self):
        producers = [{"type": "theory"}]
        consumers = [{"type": "data"}]
        mismatches = check_signal_compatibility(producers, consumers)
        assert len(mismatches) == 1
        assert "data" in mismatches[0]

    def test_empty_consumers(self):
        producers = [{"type": "theory"}]
        mismatches = check_signal_compatibility(producers, [])
        assert mismatches == []

    def test_empty_producers(self):
        consumers = [{"type": "theory"}]
        mismatches = check_signal_compatibility([], consumers)
        assert len(mismatches) == 1

    def test_both_empty(self):
        mismatches = check_signal_compatibility([], [])
        assert mismatches == []

    def test_string_entries(self):
        producers = [{"type": "theory"}]
        consumers = ["theory"]
        mismatches = check_signal_compatibility(producers, consumers)
        assert mismatches == []

    def test_string_producer_entries(self):
        producers = ["theory"]
        consumers = [{"type": "theory"}]
        mismatches = check_signal_compatibility(producers, consumers)
        assert mismatches == []

    def test_invalid_consumer_entry(self):
        mismatches = check_signal_compatibility([], [42])
        assert len(mismatches) == 1
        assert "invalid" in mismatches[0]

    def test_multiple_mismatches(self):
        producers = [{"type": "theory"}]
        consumers = [{"type": "data"}, {"type": "events"}]
        mismatches = check_signal_compatibility(producers, consumers)
        assert len(mismatches) == 2


# ---------------------------------------------------------------------------
# check_promotion_contract_monotonicity
# ---------------------------------------------------------------------------

class TestPromotionMonotonicity:
    def test_identical_seeds(self):
        seed = {"produces": [{"type": "theory"}]}
        assert check_promotion_contract_monotonicity(seed, seed) is True

    def test_additive_change(self):
        prev = {"produces": [{"type": "theory"}]}
        curr = {"produces": [{"type": "theory"}, {"type": "data"}]}
        assert check_promotion_contract_monotonicity(curr, prev) is True

    def test_removal_fails(self):
        prev = {"produces": [{"type": "theory"}, {"type": "data"}]}
        curr = {"produces": [{"type": "theory"}]}
        assert check_promotion_contract_monotonicity(curr, prev) is False

    def test_empty_previous(self):
        prev = {"produces": []}
        curr = {"produces": [{"type": "theory"}]}
        assert check_promotion_contract_monotonicity(curr, prev) is True

    def test_empty_current(self):
        prev = {"produces": [{"type": "theory"}]}
        curr = {"produces": []}
        assert check_promotion_contract_monotonicity(curr, prev) is False

    def test_no_produces_key(self):
        prev = {}
        curr = {"produces": [{"type": "theory"}]}
        assert check_promotion_contract_monotonicity(curr, prev) is True

    def test_string_entries_handled(self):
        prev = {"produces": ["theory"]}
        curr = {"produces": ["theory", "data"]}
        assert check_promotion_contract_monotonicity(curr, prev) is True

    def test_string_removal_detected(self):
        prev = {"produces": ["theory", "data"]}
        curr = {"produces": ["theory"]}
        assert check_promotion_contract_monotonicity(curr, prev) is False

    def test_both_empty(self):
        assert check_promotion_contract_monotonicity({}, {}) is True


# ---------------------------------------------------------------------------
# Canonical signal types
# ---------------------------------------------------------------------------

class TestCanonicalSignalTypes:
    def test_is_frozenset(self):
        assert isinstance(CANONICAL_SIGNAL_TYPES, frozenset)

    def test_known_types_present(self):
        assert "ONT_FRAGMENT" in CANONICAL_SIGNAL_TYPES
        assert "RULE_PROPOSAL" in CANONICAL_SIGNAL_TYPES
        assert "ANNOTATED_CORPUS" in CANONICAL_SIGNAL_TYPES

    def test_count(self):
        assert len(CANONICAL_SIGNAL_TYPES) == 14
