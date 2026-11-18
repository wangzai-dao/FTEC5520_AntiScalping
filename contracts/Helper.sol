// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./ConcertTicket.sol";

contract Helper {
    ConcertTicket public ticket;

    constructor() {
        ticket = new ConcertTicket();
    }

    // 一键测试所有流程！
    function runAllTests() external payable {
        // 1. 创建活动
        uint256 eventId = ticket.createEvent(
            "One Click Test", 
            1 ether, 
            100, 
            block.timestamp + 10 days, 
            2, // 限购2张
            false
        );

        // 2. 买第一张票 (Helper 合约自己买)
        ticket.purchaseTickets{value: 1 ether}(eventId, 1);
        
        // 动态获取刚刚买到的票号
        uint256 currentTokenId = ticket.nextTokenId() - 1;

        // 3. 尝试买第2张票 (买2张，总共3张，触发限购拦截)
        bool limitCaught = false;
        try ticket.purchaseTickets{value: 1 ether}(eventId, 2) {
        } catch {
            limitCaught = true; 
        }
        require(limitCaught, "Limit test failed!");

        // 4. 尝试高价挂单 (1.5 ETH，超过 120% 限制)
        bool priceCaught = false;
        try ticket.listForResale(currentTokenId, 1.5 ether) {
        } catch {
            priceCaught = true;
        }
        require(priceCaught, "Price test failed!");

        // 5. 正常挂单 (1.2 ETH)
        ticket.listForResale(currentTokenId, 1.2 ether);

        // 6. 验证验票
        ticket.setVerifier(address(this), true);
        ticket.checkIn(currentTokenId);

        // 退回剩余的钱
        (bool success, ) = payable(msg.sender).call{value: address(this).balance}("");
        require(success, "Refund failed");
    }

    // 让 Helper 合约能够接收 NFT
    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return this.onERC721Received.selector;
    }
}