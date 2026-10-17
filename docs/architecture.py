"""Render docs/architecture.png. Run from the repository root:

    pip install diagrams   # also needs Graphviz (https://graphviz.org/download/)
    python docs/architecture.py
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.azure.compute import FunctionApps
from diagrams.azure.monitor import ApplicationInsights
from diagrams.azure.storage import BlobStorage, StorageAccounts
from diagrams.onprem.client import Client
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.iac import Terraform
from diagrams.onprem.vcs import Github

with Diagram(
    "Azure Functions Thumbnail Service",
    filename="docs/architecture",
    outformat="png",
    show=False,
    direction="LR",
    # curved edges keep labels attached to their arrows (the default ortho routing detaches them)
    graph_attr={"splines": "spline", "nodesep": "0.7", "ranksep": "1.4", "fontsize": "18"},
    edge_attr={"fontsize": "11"},
):
    client = Client("Client")

    github = Github("GitHub repo")
    gha = GithubActions("Release Workflow")
    terraform = Terraform("Terraform")

    github >> Edge(label="trigger") >> gha
    gha >> Edge(label="build release zip") >> github

    with Cluster("Azure"):
        function = FunctionApps("Azure Function\n/api/thumbnails")

        storage_account = StorageAccounts("Storage Account")

        with Cluster("Blob Container: images"):
            originals = BlobStorage("originals/")
            thumbnails = BlobStorage("thumbnails/")
            lifecycle = BlobStorage("Lifecycle Policy\nExpire Blobs")

        insights = ApplicationInsights("Application Insights")

        storage_account >> originals
        storage_account >> thumbnails
        lifecycle >> Edge(style="dashed", label="retention_days") >> storage_account

    client >> Edge(label="POST /api/thumbnails ?code=<function key>") >> function

    function >> Edge(label="store original") >> originals
    function >> Edge(label="write thumbnail") >> thumbnails

    function >> Edge(label="telemetry") >> insights

    function >> Edge(label="thumbnail_url (SAS)") >> client

    terraform >> Edge(style="dashed", label="provisions") >> function
    terraform >> Edge(style="dashed") >> storage_account
    terraform >> Edge(style="dashed") >> lifecycle
    terraform >> Edge(style="dashed") >> insights
