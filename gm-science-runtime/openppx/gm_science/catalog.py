"""Product-owned capability catalog for gm-science."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CapabilitySource = Literal["built_in", "local", "external"]
CapabilityGroup = Literal["featured", "directory", "native"]

GM_SCIENCE_ENABLED_SKILLS_ENV = "GM_SCIENCE_ENABLED_SKILLS_JSON"


@dataclass(frozen=True, slots=True)
class ScienceCapabilityDefinition:
    """Describe one stable gm-science capability independent of its implementation."""

    id: str
    name: str
    description: str
    source: CapabilitySource = "built_in"
    group: CapabilityGroup = "featured"


BUILTIN_SCIENCE_SKILLS = (
    ScienceCapabilityDefinition("alphafold2", "AlphaFold2", "Predict protein structures with an AlphaFold2 runtime."),
    ScienceCapabilityDefinition("boltz", "Boltz", "Predict biomolecular structures and interactions with Boltz."),
    ScienceCapabilityDefinition("borzoi", "Borzoi", "Predict genomic sequence effects with Borzoi models."),
    ScienceCapabilityDefinition("chai-1", "Chai-1", "Model biomolecular structures with Chai-1."),
    ScienceCapabilityDefinition("diffdock", "DiffDock", "Predict ligand binding poses with DiffDock."),
    ScienceCapabilityDefinition("esm-2", "ESM-2", "Compute protein language-model representations with ESM-2."),
    ScienceCapabilityDefinition("esmfold2", "ESMFold2", "Predict protein structures with ESMFold2."),
    ScienceCapabilityDefinition("evo-2", "Evo 2", "Analyze and generate biological sequences with Evo 2."),
    ScienceCapabilityDefinition(
        "indication-dossier",
        "Indication Dossier",
        "Build an evidence-backed therapeutic indication dossier.",
    ),
    ScienceCapabilityDefinition(
        "ligandmpnn",
        "LigandMPNN",
        "Design protein sequences around ligands and molecular contexts.",
    ),
    ScienceCapabilityDefinition(
        "literature-review",
        "Literature Review",
        "Search scholarly sources, build an evidence matrix, and register a cited review.",
    ),
    ScienceCapabilityDefinition(
        "morning",
        "Morning",
        "Prepare a concise daily research briefing from selected sources.",
    ),
    ScienceCapabilityDefinition("openfold3", "OpenFold3", "Run open biomolecular structure prediction workflows."),
    ScienceCapabilityDefinition("proteinmpnn", "ProteinMPNN", "Design protein sequences for target structures."),
    ScienceCapabilityDefinition("scgpt", "scGPT", "Analyze single-cell data with scGPT models."),
    ScienceCapabilityDefinition(
        "scvi-tools",
        "scvi-tools",
        "Model and integrate single-cell omics data with scvi-tools.",
    ),
    ScienceCapabilityDefinition(
        "solublempnn",
        "SolubleMPNN",
        "Design protein sequences with solubility-aware constraints.",
    ),
)

BUILTIN_SCIENCE_SKILL_IDS = frozenset(
    definition.id for definition in BUILTIN_SCIENCE_SKILLS
)


SCIENCE_CONNECTORS = (
    ScienceCapabilityDefinition("biomart", "BioMart", "Query federated biological datasets through BioMart."),
    ScienceCapabilityDefinition("cancer-models", "Cancer Models", "Access cancer model and dependency datasets."),
    ScienceCapabilityDefinition("cellguide", "CellGuide", "Access cell type references and annotations."),
    ScienceCapabilityDefinition("chemistry", "Chemistry", "Search chemical entities, properties, and reactions."),
    ScienceCapabilityDefinition(
        "clinical-genomics",
        "Clinical Genomics",
        "Access clinically interpreted genomic evidence.",
    ),
    ScienceCapabilityDefinition("drug-regulatory", "Drug Regulatory", "Search drug labels and regulatory evidence."),
    ScienceCapabilityDefinition("expression", "Expression", "Query gene and transcript expression resources."),
    ScienceCapabilityDefinition(
        "genes-ontologies",
        "Genes & Ontologies",
        "Resolve genes, terms, and biological ontologies.",
    ),
    ScienceCapabilityDefinition("genomes", "Genomes", "Access reference genomes and genome annotations."),
    ScienceCapabilityDefinition("human-genetics", "Human Genetics", "Search human genetic association evidence."),
    ScienceCapabilityDefinition("ketcher-chemistry", "Ketcher Chemistry", "Edit and inspect chemical structures."),
    ScienceCapabilityDefinition(
        "literature-graph",
        "Literature Graph",
        "Traverse publications, citations, authors, and concepts.",
    ),
    ScienceCapabilityDefinition("omics-archives", "Omics Archives", "Search public omics study archives."),
    ScienceCapabilityDefinition(
        "protein-annotation",
        "Protein Annotation",
        "Access protein function and annotation resources.",
    ),
    ScienceCapabilityDefinition("regulation", "Regulation", "Query transcriptional and epigenetic regulation data."),
    ScienceCapabilityDefinition(
        "research-resources",
        "Research Resources",
        "Search broad scientific repositories and identifiers.",
    ),
    ScienceCapabilityDefinition("rna", "RNA", "Access RNA sequence, structure, and function resources."),
    ScienceCapabilityDefinition(
        "structures-interactions",
        "Structures & Interactions",
        "Search molecular structures and interaction evidence.",
    ),
    ScienceCapabilityDefinition("variants", "Variants", "Query genomic variants and annotations."),
    ScienceCapabilityDefinition("zinc", "ZINC", "Search purchasable compounds from ZINC."),
    ScienceCapabilityDefinition(
        "biorxiv",
        "bioRxiv",
        "Search life-science preprints from bioRxiv.",
        "external",
        "directory",
    ),
    ScienceCapabilityDefinition(
        "chembl",
        "ChEMBL",
        "Search bioactive molecules and assay data from ChEMBL.",
        "external",
        "directory",
    ),
    ScienceCapabilityDefinition(
        "clinical-trials",
        "Clinical Trials",
        "Search registered clinical studies.",
        "external",
        "directory",
    ),
    ScienceCapabilityDefinition(
        "pubmed",
        "PubMed",
        "Search biomedical literature indexed by PubMed.",
        "external",
        "directory",
    ),
    ScienceCapabilityDefinition(
        "arxiv",
        "arXiv",
        "Search open-access preprints across scientific and technical fields.",
        "external",
        "native",
    ),
    ScienceCapabilityDefinition(
        "openalex",
        "OpenAlex",
        "Search scholarly works and citation metadata from OpenAlex.",
        "external",
        "native",
    ),
)
