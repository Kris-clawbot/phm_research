from __future__ import annotations

import re
from dataclasses import dataclass


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


@dataclass
class Taxonomy:
    task_types: list[str]
    hybrid_types: list[str]
    case_study: str | None
    methods: list[str]


TASK_PATTERNS: list[tuple[str, list[str]]] = [
    ("prognostics", ["remaining useful life", "rul", "end-of-life", "eol", "time-to-failure", "ttf", "prognostic"]),
    ("fault_detection", ["fault detection", "fault diagnosis", "fault identification"]),
    ("anomaly_detection", ["anomaly", "novelty detection", "outlier"]),
    ("diagnostics", ["diagnosis", "diagnostic", "fault isolation", "fault classification"]),
]

HYBRID_PATTERNS: list[tuple[str, list[str]]] = [
    ("physics_informed", ["physics-informed", "physics informed", "pinn", "physical constraint", "governing equation"]),
    ("grey_box", ["grey-box", "gray-box", "semi-physical", "semi physical"]),
    ("digital_twin", ["digital twin"]),
    ("residual_learning", ["residual", "model correction", "error compensation"]),
    ("bayesian_hybrid", ["bayesian", "prior knowledge", "prior", "probabilistic"]),
    ("state_space", ["state-space", "state space", "kalman", "particle filter", "hidden markov"]),
]

METHOD_PATTERNS: list[tuple[str, list[str]]] = [
    ("lstm", ["lstm", "long short-term memory"]),
    ("transformer", ["transformer", "attention"]),
    ("cnn", ["cnn", "convolutional"]),
    ("gaussian_process", ["gaussian process", "gp regression"]),
    ("kalman_filter", ["kalman"]),
    ("particle_filter", ["particle filter"]),
    ("bayesian", ["bayesian", "variational", "mcmc"]),
    ("pinn", ["pinn", "physics-informed neural network"]),
]

CASE_STUDY_PATTERNS: list[tuple[str, list[str]]] = [
    ("bearings", ["bearing", "rolling element bearing"]),
    ("batteries", ["battery", "lithium-ion", "li-ion", "state of health", "soh"]),
    ("wind_turbines", ["wind turbine"]),
    ("turbofan_engines", ["turbofan", "nasa cmapss", "c-mapss", "cmapss"]),
    ("gearboxes", ["gearbox", "gear"]),
    ("motors", ["induction motor", "electric motor"]),
    ("rail", ["rail", "wheel", "axle"]),
]


def _match_many(text: str, patterns: list[tuple[str, list[str]]]) -> list[str]:
    out = []
    for label, kws in patterns:
        if any(kw in text for kw in kws):
            out.append(label)
    return out


def classify(title: str | None, abstract: str | None) -> Taxonomy:
    text = _norm((title or "") + "\n" + (abstract or ""))

    task = _match_many(text, TASK_PATTERNS)
    hybrid = _match_many(text, HYBRID_PATTERNS)
    methods = _match_many(text, METHOD_PATTERNS)

    case = None
    for label, kws in CASE_STUDY_PATTERNS:
        if any(kw in text for kw in kws):
            case = label
            break

    # basic defaults
    if not task and ("prognostic" in text or "rul" in text):
        task = ["prognostics"]

    return Taxonomy(task_types=task, hybrid_types=hybrid, case_study=case, methods=methods)
