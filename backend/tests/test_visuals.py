from app.services.visuals import coerce_visual


class TestCoerceVisual:
    def test_valid_math_steps_kept(self):
        v = coerce_visual({
            "focus": "convolution arithmetic",
            "steps": [
                {"caption": "Multiply the patch by the filter", "math": "\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}", "diagram": ""},
                {"caption": "Sum and place the value", "math": "1+1=2", "diagram": ""},
            ],
        })
        assert v is not None
        assert v["focus"] == "convolution arithmetic"
        assert len(v["steps"]) == 2

    def test_captions_only_rejected(self):
        v = coerce_visual({
            "focus": "x",
            "steps": [{"caption": "a long caption describing something in plain words only", "math": "", "diagram": ""}],
        })
        assert v is None  # no math and no diagram anywhere → not a visual

    def test_invalid_diagram_never_ships(self):
        v = coerce_visual({
            "focus": "flow",
            "steps": [
                {"caption": "valid math step", "math": "a+b", "diagram": ""},
                {"caption": "broken diagram step", "math": "", "diagram": "graph TB; A[x-->B"},
            ],
        })
        assert v is not None
        # The broken diagram is stripped; a step left with nothing visual is dropped.
        assert len(v["steps"]) == 1
        assert all("A[x" not in s["diagram"] for s in v["steps"])

    def test_valid_diagram_kept(self):
        v = coerce_visual({
            "focus": "flow",
            "steps": [{"caption": "the request path", "math": "", "diagram": "graph TB; A[Client]-->|asks| B[Server]"}],
        })
        assert v is not None
        assert v["steps"][0]["diagram"].startswith("graph TB")

    def test_garbage_shapes_survive(self):
        assert coerce_visual({}) is None
        assert coerce_visual({"steps": ["not a dict", 42]}) is None
