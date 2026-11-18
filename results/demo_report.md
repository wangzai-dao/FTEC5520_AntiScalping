# FTEC5520 Anti-Scalping Ticketing System - on-chain evidence

- Generated at: 2026-11-18T11:28:47+00:00
- Network: private chain, chainId `1337`, RPC `http://127.0.0.1:8545`
- Contract address: `0x5182970de64BDb93357aDbCd984F6A4F0484bBB2`
- Deployment tx: `0x4113911dced9e247996a0c0cc998cef78bc03b699cadf400fb0d23bb943a5106` (block 6)

## Test detail

| ID | Scenario | Actor | Expected | Actual | Result | Tx hash | Block | Gas |
|---|---|---|---|---|---|---|---|---|
| T01 | Create event (1 ETH / 100 tickets / limit 2) | organizer | success | success | PASS | `0xe0b7b5f6c77b9fa199ade7c37cd7751f3f669a62046dcdfda78d60417f0418d4` | 8 | 168344 |
| T01b | Create near-event event (0.5 ETH / 3 days out) | organizer | success | success | PASS | `0x8749683091786bbb72c0025ec2b7abfab5932b3daac8fe577f57e37da7466a96` | 10 | 168368 |
| T01c | Create presale event (presaleActive=true) | organizer | success | success | PASS | `0x7a9c287d18816aa35f09e3454d8669808235451266c811cf4bef69d670e2cd09` | 12 | 168248 |
| T02 | Batch whitelist buyerA / buyerB | organizer | success | success | PASS | `0x3e894770b343639ae0162692d06648a0739993993a8872fa642fcc637ef9eaeb` | 14 | 75385 |
| T03 | buyerA buys 1 ticket during presale | buyerA | success | success | PASS | `0x6f861c7e12c407e5a49103fada72f5544bde287393eae31bea3c18f9ccedd347` | 16 | 191471 |
| T04 | attacker (not whitelisted) buys during presale | attacker | failure | rejected: Wallet is not whitelisted | PASS | `-` | - | - |
| T05a | buyerA buys 1 ticket (event 1) | buyerA | success | success | PASS | `0xd67e2cbf0f77cfe93ccd119e48936e5a5a04ccab447589093e4271fa4a4b737b` | 18 | 155012 |
| T05b | buyerA buys a second ticket (reaches the limit) | buyerA | success | success | PASS | `0x820bd8df534aebd6718047ac9d44ba983d126e207ffa5ba6a316b4a4066e63b3` | 20 | 120812 |
| T05c | buyerB buys 1 ticket (event 1) | buyerB | success | success | PASS | `0x3dbbc844e36bcdd17a93e53560a231be3ee99a19601674c79052bb580e4e5ef6` | 22 | 155012 |
| T06 | attacker tries to buy 3 tickets (limit is 2) | attacker | failure | rejected: Wallet limit exceeded | PASS | `-` | - | - |
| T06b | attacker buys the only ticket | attacker | success | success | PASS | `0x6d60f818fa1e7975c83a9d6ea12238f6da3defabdc2c77e1d49fdeb52cdd85da` | 26 | 189212 |
| T06c | buyerB buys after the event sold out | buyerB | failure | rejected: Not enough tickets | PASS | `-` | - | - |
| T11 | holder calls transferFrom directly to move the ticket | buyerA | failure | rejected: execution reverted (status=0) | PASS | `0xcbcab7935a387664fef1cc269224274e89e90af87ff6cc1a8cc201d259d33632` | 28 | 22546 |
| T08 | buyerA lists at 1.5 ETH (original price 1 ETH) | buyerA | failure | rejected: Price exceeds dynamic limit | PASS | `-` | - | - |
| T12 | attacker lists a ticket it does not own | attacker | failure | rejected: Not the owner | PASS | `-` | - | - |
| T09a | buyerB buys a ticket of event 2 | buyerB | success | success | PASS | `0x2056af70f32eec1923b0ac30bb4d9aba308043f4c02666f3a51e66b5c05b80ec` | 30 | 155012 |
| T09 | 3 days out, lists at 0.6 ETH (cap 0.5) | buyerB | failure | rejected: Price exceeds dynamic limit | PASS | `-` | - | - |
| T09b | 3 days out, lists at 0.5 ETH (= 100%) | buyerB | success | success | PASS | `0xa3aa98baa5502a0115859d485e2d951f4dfc3a3e5f6b139a0ca7ca03aebf7e59` | 32 | 79734 |
| T07a | buyerA lists at 1.2 ETH (= 120%) | buyerA | success | success | PASS | `0x6e234957c9027b336c4bcba81cc7fee5c8f225478f6a0c32b5cf9d22847d1494` | 34 | 79891 |
| T07 | buyerB buys the resale listing | buyerB | success | success | PASS | `0x253585f22f5ff8a523f14f8fad1d01741aa61e05f7b66f5fe2af6e0e3a8e9f12` | 36 | 110677 |
| T10 | fourth listing (resaleCount already 3) | buyerB | failure | rejected: Max resale limit reached | PASS | `-` | - | - |
| T17 | attacker (unauthorised) calls checkIn | attacker | failure | rejected: Not an authorized verifier | PASS | `-` | - | - |
| T13 | owner authorises the verifier | deployer | success | success | PASS | `0x683c13d57fdfb7e1def4840f6c28ce9b4641f27c4389ffb5d92168de2cb2be98` | 46 | 47923 |
| T15 | verifier checks the ticket in for the first time | verifier | success | success | PASS | `0x183e9fdecddd3c65d3385863147e31a1c6767f824217488ae32a9e24d749177b` | 48 | 51851 |
| T16 | second check-in of the same ticket | verifier | failure | rejected: Ticket already used | PASS | `-` | - | - |
| T07c | attacker buys 1 ticket of event 1 as a display item | attacker | success | success | PASS | `0x9f2962bc204aaa2e42b3332df4954c7fe8965b1ad34690c7e36619756913aa96` | 50 | 137912 |
| T07d | that ticket is listed at 1.2 ETH (kept for the demo pages) | attacker | success | success | PASS | `0x170a93401406d314961867429dc7e6e2667b209c39c15e8de10a7892fbc907a1` | 52 | 79891 |

## Summary

- Operations: 27, pass 27, fail 0
- Final block: 52
- Tickets minted: 8, currently listed: [6, 8]

> Note: the pass flag respects the expected direction - a case expected to fail only counts as PASS when the contract really rejected it.