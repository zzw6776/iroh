# EcoPaste Iroh fork

This fork follows published Iroh 1.x stable releases on the `ecopaste` branch.
The original source and licenses are retained. EcoPaste clients and the Hub pin
an exact reviewed commit rather than following a moving branch.

## GSO carry patch

`patches/gso-live-limit.patch` is the fix proposed in
[n0-computer/iroh#4645](https://github.com/n0-computer/iroh/pull/4645), for
[n0-computer/iroh#4555](https://github.com/n0-computer/iroh/issues/4555).
Credit belongs to the upstream patch author and reviewers.

An existing sender now reads the IP socket's current segmentation limit. When
noq-udp disables GSO after EIO/EINVAL, existing QUIC connections follow the new
limit and ordinary QUIC retransmission recovers dropped packets. This does not
make an unsupported device support GSO, nor add a second reconnect mechanism.

The real socket regression forces EINVAL on loopback and checks that an already
created sender immediately observes the reduced limit. It runs on Linux CI and
can also run on Android. The ignored Android diagnostic additionally exercises
an actual VPN EIO using `ECOPASTE_GSO_PROBE_ADDRESS`, then reuses the same sender.

## Automatic updates

`Sync Upstream Stable` runs daily at 03:37 UTC and supports manual dispatch.
It fetches the latest published stable release, reconstructs the upstream tree,
reapplies this overlay, and opens an update PR. Only this fork's workflows are
installed: upstream publication and self-hosted workflows are excluded.

The PR automatically merges only after the required `Fork validation` check
passes on Linux, macOS, Windows and an Android arm64 release compilation. The GSO socket regression and overlay tests
must pass. `workflow_dispatch` starts these checks explicitly because a PR made
with GITHUB_TOKEN does not itself start another workflow.

Patch conflicts, missing regressions, failed checks, or a new upstream major
version leave the existing branch unchanged. If upstream incorporates the exact
patch, the updater recognizes it and keeps following the fork without applying
it twice. The checked-in `upstream.json` records upstream provenance.
