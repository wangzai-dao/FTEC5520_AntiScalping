// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./ConcertTicket.sol";

contract Helper {
    ConcertTicket public ticket;

    constructor() {
        ticket = new ConcertTicket();
    }

    // One click runs the whole flow.
    function runAllTests() external payable {
        // 1. Create an event
        uint256 eventId = ticket.createEvent(
            "One Click Test",
            1 ether,
            100,
            block.timestamp + 10 days,
            2, // wallet limit of 2 tickets
            false
        );

        // 2. Buy the first ticket (the Helper contract buys it itself)
        ticket.purchaseTickets{value: 1 ether}(eventId, 1);

        // Read the token id that was just minted
        uint256 currentTokenId = ticket.nextTokenId() - 1;

        // 3. Try to buy two more tickets (3 in total, so the wallet limit must reject it)
        bool limitCaught = false;
        try ticket.purchaseTickets{value: 1 ether}(eventId, 2) {
        } catch {
            limitCaught = true;
        }
        require(limitCaught, "Limit test failed!");

        // 4. Try an over-priced listing (1.5 ETH, above the 120% cap)
        bool priceCaught = false;
        try ticket.listForResale(currentTokenId, 1.5 ether) {
        } catch {
            priceCaught = true;
        }
        require(priceCaught, "Price test failed!");

        // 5. List at a legal price (1.2 ETH)
        ticket.listForResale(currentTokenId, 1.2 ether);

        // 6. Verify and check in
        ticket.setVerifier(address(this), true);
        ticket.checkIn(currentTokenId);

        // Refund the remaining balance
        (bool success, ) = payable(msg.sender).call{value: address(this).balance}("");
        require(success, "Refund failed");
    }

    // Lets the Helper contract receive NFTs
    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return this.onERC721Received.selector;
    }
}
