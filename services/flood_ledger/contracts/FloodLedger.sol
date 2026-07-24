// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title FloodLedger
 * @notice Parametric flood insurance oracle — records flood events
 *         and triggers automatic payouts when threshold is breached.
 */
contract FloodLedger {
    struct FloodEvent {
        uint256 id;
        string basinId;
        uint256 timestamp;
        uint256 riskScore;      // basis points (0-10000 = 0-100%)
        string alertLevel;      // NORMAL, ADVISORY, WATCH, WARNING, EMERGENCY
        bool payoutTriggered;
        uint256 payoutAmountWei;
    }

    address public owner;
    uint256 public eventCount;
    uint256 public payoutThreshold;  // risk score threshold in basis points

    mapping(uint256 => FloodEvent) public events;
    mapping(address => uint256) public insuredBalances;

    event FloodRecorded(uint256 indexed eventId, string basinId, uint256 riskScore, string alertLevel);
    event PayoutTriggered(uint256 indexed eventId, uint256 amount);
    event FundsDeposited(address indexed from, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    constructor(uint256 _payoutThresholdBps) {
        owner = msg.sender;
        payoutThreshold = _payoutThresholdBps;
    }

    /**
     * @notice Record a flood event from the ARGUS prediction engine.
     * @param basinId River basin identifier
     * @param riskScore Risk score in basis points (0-10000)
     * @param alertLevel Alert level string
     */
    function recordFloodEvent(
        string memory basinId,
        uint256 riskScore,
        string memory alertLevel
    ) external onlyOwner returns (uint256) {
        eventCount++;
        bool trigger = riskScore >= payoutThreshold;

        events[eventCount] = FloodEvent({
            id: eventCount,
            basinId: basinId,
            timestamp: block.timestamp,
            riskScore: riskScore,
            alertLevel: alertLevel,
            payoutTriggered: trigger,
            payoutAmountWei: trigger ? address(this).balance / 10 : 0
        });

        emit FloodRecorded(eventCount, basinId, riskScore, alertLevel);

        if (trigger && address(this).balance > 0) {
            uint256 payout = address(this).balance / 10;
            payable(owner).transfer(payout);
            emit PayoutTriggered(eventCount, payout);
        }

        return eventCount;
    }

    /**
     * @notice Get details of a recorded flood event.
     */
    function getEvent(uint256 eventId) external view returns (FloodEvent memory) {
        require(eventId > 0 && eventId <= eventCount, "Invalid event ID");
        return events[eventId];
    }

    /**
     * @notice Update the payout threshold.
     */
    function setPayoutThreshold(uint256 _thresholdBps) external onlyOwner {
        payoutThreshold = _thresholdBps;
    }

    /**
     * @notice Deposit insurance funds into the contract.
     */
    function deposit() external payable {
        emit FundsDeposited(msg.sender, msg.value);
    }

    /**
     * @notice Get contract balance.
     */
    function getBalance() external view returns (uint256) {
        return address(this).balance;
    }

    receive() external payable {}
}
