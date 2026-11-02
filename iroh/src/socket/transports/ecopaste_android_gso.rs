//! Explicit diagnostic for Android VPN routes whose TUN device rejects segmented UDP.
use super::*;

#[tokio::test]
#[ignore = "requires an Android VPN route without TX checksum offload"]
async fn vpn_eio_updates_an_already_created_sender() {
    let transports = Transports {
        ip: IpTransports::bind(
            std::iter::once(IpConfig::V4 {
                ip_net: "0.0.0.0/0".parse().unwrap(),
                port: 0,
                is_required: true,
                is_default: true,
            }),
            &EndpointMetrics::default(),
        )
        .unwrap(),
        relay: Vec::new(),
        custom: Vec::new(),
        poll_recv_counter: 0,
        recv_infos: Default::default(),
        consecutive_total_recv_failures: 0,
    };
    let mut sender = transports.create_sender();
    assert!(sender.max_transmit_segments().get() > 1);
    let destination = std::env::var("ECOPASTE_GSO_PROBE_ADDRESS")
        .expect("set the known VPN-routed diagnostic destination")
        .parse()
        .unwrap();
    let path = FourTuple::Ip {
        remote: destination,
        local: None,
    };
    let contents = [0u8; 2400];
    let segmented = Transmit {
        ecn: None,
        contents: &contents,
        segment_size: Some(1200),
    };
    std::future::poll_fn(|cx| Pin::new(&mut sender).poll_send(cx, &path, &segmented))
        .await
        .unwrap();
    assert_eq!(sender.max_transmit_segments(), NonZeroUsize::MIN);
    let ordinary = Transmit {
        ecn: None,
        contents: &contents[..1200],
        segment_size: None,
    };
    std::future::poll_fn(|cx| Pin::new(&mut sender).poll_send(cx, &path, &ordinary))
        .await
        .unwrap();
    assert_eq!(sender.max_transmit_segments(), NonZeroUsize::MIN);
}
