// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts@5.0.2/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts@5.0.2/access/Ownable.sol";
import "@openzeppelin/contracts@5.0.2/utils/ReentrancyGuard.sol";

/**
 * @title Anti-Scalping Concert Ticket System
 * @dev Merges Member 2's primary ticketing logic with Member 3's anti-scalping, 
 * resale, and check-in features.
 */
contract ConcertTicket is ERC721, Ownable, ReentrancyGuard {
    
    // ==========================================
    // 1. Data Structures
    // ==========================================

    // [Member 2] Concert event information
    struct ConcertEvent {
        string name;        
        uint256 price;      
        uint256 maxSupply;  
        uint256 sold;       
        uint256 eventTime;  
        uint256 walletLimit;
        address organizer;  
        bool active;        
        bool presaleActive; 
    }

    // [Member 3] Ticket state for resale and check-in
    struct TicketInfo {
        bool isListed;       
        uint256 listingPrice;
        uint256 resaleCount; 
        bool used;           
    }

    uint256 public nextEventId = 1; 
    uint256 public nextTokenId = 1; 

    // [Member 2] Mappings
    mapping(uint256 => ConcertEvent) public concertEvents;
    mapping(uint256 => mapping(address => bool)) public whitelist; 
    mapping(uint256 => mapping(address => uint256)) public purchasedByWallet;
    mapping(uint256 => uint256) public tokenToEvent; 
    mapping(address => uint256) public pendingProceeds; 

    // [Member 3] Mappings
    mapping(uint256 => TicketInfo) public tickets; 
    mapping(address => bool) public verifiers;     
    mapping(address => uint256) public pendingPlatformFees; 

    // ==========================================
    // 2. Events
    // ==========================================
    event ConcertEventCreated(uint256 indexed eventId, address indexed organizer, string name, uint256 price, uint256 maxSupply, uint256 eventTime, uint256 walletLimit, bool presaleActive);
    event EventStatusChanged(uint256 indexed eventId, bool active);
    event PresaleStatusChanged(uint256 indexed eventId, bool presaleActive);
    event WhitelistUpdated(uint256 indexed eventId, address indexed account, bool allowed);
    event TicketPurchased(uint256 indexed eventId, address indexed buyer, uint256 quantity, uint256 totalPaid, uint256 firstTokenId, uint256 lastTokenId);
    event ProceedsWithdrawn(address indexed organizer, uint256 amount);
    
    // [Member 3] Events
    event TicketResold(uint256 indexed tokenId, address indexed seller, address indexed buyer, uint256 price, uint256 platformFee);
    event TicketCheckedIn(uint256 indexed tokenId, address indexed verifier); 
    event VerifierStatusChanged(address indexed verifier, bool status);

    // ==========================================
    // 3. Constructor & Modifiers
    // ==========================================
    constructor() ERC721("Concert Ticket", "CTIX") Ownable(msg.sender) {}

    modifier onlyEventManager(uint256 eventId) {
        require(concertEvents[eventId].organizer != address(0), "Event does not exist");
        require(msg.sender == concertEvents[eventId].organizer || msg.sender == owner(), "Not event manager");
        _;
    }

    // ==========================================
    // 4. Member 2's Logic
    // ==========================================

    function createEvent(
        string calldata name, uint256 price, uint256 maxSupply, 
        uint256 eventTime, uint256 walletLimit, bool presaleActive
    ) external returns (uint256 eventId) {
        require(bytes(name).length > 0, "Name is empty");
        require(price > 0, "Price must be greater than zero");
        require(maxSupply > 0, "Supply must be greater than zero");
        require(eventTime > block.timestamp, "Event time must be future");
        require(walletLimit > 0, "Wallet limit must be greater than zero");
        require(walletLimit <= maxSupply, "Wallet limit exceeds supply");

        eventId = nextEventId;
        nextEventId++;
        concertEvents[eventId] = ConcertEvent(name, price, maxSupply, 0, eventTime, walletLimit, msg.sender, true, presaleActive);
        emit ConcertEventCreated(eventId, msg.sender, name, price, maxSupply, eventTime, walletLimit, presaleActive);
    }

    function setEventActive(uint256 eventId, bool active) external onlyEventManager(eventId) {
        concertEvents[eventId].active = active;
        emit EventStatusChanged(eventId, active);
    }

    function setPresaleActive(uint256 eventId, bool presaleActive) external onlyEventManager(eventId) {
        concertEvents[eventId].presaleActive = presaleActive;
        emit PresaleStatusChanged(eventId, presaleActive);
    }

    function setWhitelist(uint256 eventId, address account, bool allowed) external onlyEventManager(eventId) {
        require(account != address(0), "Invalid account");
        whitelist[eventId][account] = allowed;
        emit WhitelistUpdated(eventId, account, allowed);
    }

    function setWhitelistBatch(uint256 eventId, address[] calldata accounts, bool allowed) external onlyEventManager(eventId) {
        require(accounts.length > 0, "Empty account list");
        for (uint256 i = 0; i < accounts.length; i++) {
            require(accounts[i] != address(0), "Invalid account");
            whitelist[eventId][accounts[i]] = allowed;
            emit WhitelistUpdated(eventId, accounts[i], allowed);
        }
    }

    function purchaseTickets(uint256 eventId, uint256 quantity) external payable nonReentrant {
        ConcertEvent storage concert = concertEvents[eventId];
        require(concert.organizer != address(0), "Event does not exist");
        require(concert.active, "Event is not active");
        require(block.timestamp < concert.eventTime, "Event already started");
        require(quantity > 0, "Quantity must be greater than zero");
        require(concert.sold + quantity <= concert.maxSupply, "Not enough tickets");
        require(purchasedByWallet[eventId][msg.sender] + quantity <= concert.walletLimit, "Wallet limit exceeded");

        if (concert.presaleActive) {
            require(whitelist[eventId][msg.sender], "Wallet is not whitelisted");
        }

        uint256 totalPrice = concert.price * quantity;
        require(msg.value == totalPrice, "Incorrect ETH amount");

        concert.sold += quantity;
        purchasedByWallet[eventId][msg.sender] += quantity;
        pendingProceeds[concert.organizer] += totalPrice;

        uint256 firstTokenId = nextTokenId;

        for (uint256 i = 0; i < quantity; i++) {
            uint256 tokenId = nextTokenId;
            nextTokenId++;
            tokenToEvent[tokenId] = eventId;
            
            tickets[tokenId] = TicketInfo({
                isListed: false,
                listingPrice: 0,
                resaleCount: 0,
                used: false
            });

            _safeMint(msg.sender, tokenId);
        }

        emit TicketPurchased(eventId, msg.sender, quantity, totalPrice, firstTokenId, nextTokenId - 1);
    }

    function withdrawProceeds() external nonReentrant {
        uint256 amount = pendingProceeds[msg.sender];
        require(amount > 0, "No proceeds available");
        pendingProceeds[msg.sender] = 0;
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "ETH transfer failed");
        emit ProceedsWithdrawn(msg.sender, amount);
    }

    function remainingSupply(uint256 eventId) external view returns (uint256) {
        return concertEvents[eventId].maxSupply - concertEvents[eventId].sold;
    }

    function canPurchase(uint256 eventId, address account, uint256 quantity) external view returns (bool, string memory) {
        ConcertEvent storage concert = concertEvents[eventId];
        if (concert.organizer == address(0)) return (false, "Event does not exist");
        if (!concert.active) return (false, "Event is not active");
        if (block.timestamp >= concert.eventTime) return (false, "Event already started");
        if (quantity == 0) return (false, "Quantity is zero");
        if (concert.sold + quantity > concert.maxSupply) return (false, "Not enough tickets");
        if (purchasedByWallet[eventId][account] + quantity > concert.walletLimit) return (false, "Wallet limit exceeded");
        if (concert.presaleActive && !whitelist[eventId][account]) return (false, "Wallet is not whitelisted");
        return (true, "Purchase allowed");
    }

    // ==========================================
    // 5. Member 3's Logic
    // ==========================================

    function setVerifier(address _verifier, bool _status) external onlyOwner {
        require(_verifier != address(0), "Invalid address");
        verifiers[_verifier] = _status;
        emit VerifierStatusChanged(_verifier, _status);
    }

    function getMaxResalePrice(uint256 tokenId) public view returns (uint256) {
        uint256 eventId = tokenToEvent[tokenId];
        ConcertEvent storage concert = concertEvents[eventId];
        uint256 originalPrice = concert.price;

        if (concert.eventTime - block.timestamp <= 7 days) {
            return originalPrice; 
        } else {
            return (originalPrice * 120) / 100; 
        }
    }

    function listForResale(uint256 tokenId, uint256 price) external {
        require(ownerOf(tokenId) == msg.sender, "Not the owner"); 
        TicketInfo storage ticket = tickets[tokenId];
        uint256 eventId = tokenToEvent[tokenId];
        
        require(!ticket.used, "Ticket already used"); 
        require(!ticket.isListed, "Already listed"); 
        require(ticket.resaleCount < 3, "Max resale limit reached"); 
        require(block.timestamp < concertEvents[eventId].eventTime, "Event already started");
        
        uint256 maxPrice = getMaxResalePrice(tokenId);
        require(price > 0 && price <= maxPrice, "Price exceeds dynamic limit");

        ticket.isListed = true;
        ticket.listingPrice = price;
    }

    function cancelListing(uint256 tokenId) external {
        require(ownerOf(tokenId) == msg.sender, "Not the owner");
        TicketInfo storage ticket = tickets[tokenId];
        require(ticket.isListed, "Not listed");
        
        ticket.isListed = false;
        ticket.listingPrice = 0;
    }

    function buyResale(uint256 tokenId) external payable nonReentrant {
        TicketInfo storage ticket = tickets[tokenId];
        address seller = ownerOf(tokenId);
        uint256 eventId = tokenToEvent[tokenId];
        ConcertEvent storage concert = concertEvents[eventId];

        require(ticket.isListed, "Not listed for resale");
        require(!ticket.used, "Ticket already used");
        require(msg.sender != seller, "Cannot buy your own ticket");
        require(msg.value == ticket.listingPrice, "Incorrect payment amount");
        require(ticket.resaleCount < 3, "Max resale limit reached");

        if (concert.presaleActive) {
            require(whitelist[eventId][msg.sender], "Buyer not in presale whitelist");
        }

        ticket.isListed = false;
        ticket.resaleCount++;
        uint256 price = ticket.listingPrice;
        ticket.listingPrice = 0;

        uint256 platformFee = (price * 5) / 100; 
        uint256 sellerAmount = price - platformFee; 

        pendingPlatformFees[owner()] += platformFee; 

        _transfer(seller, msg.sender, tokenId);
        
        (bool success, ) = payable(seller).call{value: sellerAmount}("");
        require(success, "Payment to seller failed");

        emit TicketResold(tokenId, seller, msg.sender, price, platformFee);
    }

    function withdrawPlatformFees() external onlyOwner nonReentrant {
        uint256 amount = pendingPlatformFees[msg.sender];
        require(amount > 0, "No platform fees available");
        pendingPlatformFees[msg.sender] = 0;
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "Platform fee transfer failed");
    }

    function checkIn(uint256 tokenId) external {
        require(verifiers[msg.sender], "Not an authorized verifier"); 
        
        TicketInfo storage ticket = tickets[tokenId];
        require(_ownerOf(tokenId) != address(0), "Ticket does not exist");
        require(!ticket.used, "Ticket already used"); 

        if (ticket.isListed) {
            ticket.isListed = false;
            ticket.listingPrice = 0;
        }

        ticket.used = true;
        emit TicketCheckedIn(tokenId, msg.sender); 
    }

    // ==========================================
    // 6. Member 3's Ultimate Defense
    // ==========================================

    function transferFrom(address /*from*/, address /*to*/, uint256 /*tokenId*/) public virtual override {
        revert("Direct transfer is disabled. Use listForResale and buyResale.");
    }

    function safeTransferFrom(address /*from*/, address /*to*/, uint256 /*tokenId*/, bytes memory /*data*/) public virtual override {
        revert("Direct transfer is disabled. Use listForResale and buyResale.");
    }
}