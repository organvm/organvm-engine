// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TestamentRegistry
 * @notice Stores Ring 4 (external chain) anchors for the Testament Protocol.
 *         Anchors are a single SHA-256 hash representing a Merkle checkpoint
 *         of events, placed onto a public L2 (e.g., Base).
 */
contract TestamentRegistry {
    address public owner;

    struct Anchor {
        bytes32 merkleRoot;
        bytes32 chainTipHash;
        uint256 sequenceStart;
        uint256 sequenceEnd;
        uint256 eventCount;
        uint256 timestamp;
        bytes32 anchorHash;
    }

    mapping(bytes32 => Anchor) public anchors;

    event AnchorRegistered(bytes32 indexed anchorHash, bytes32 indexed merkleRoot);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    /**
     * @notice Register a new anchor.
     * @param merkleRoot The Merkle root of the checkpointed events.
     * @param chainTipHash The hash of the last event in the chain.
     * @param sequenceStart First event sequence number in the batch.
     * @param sequenceEnd Last event sequence number in the batch.
     * @param eventCount Number of events in the batch.
     * @param timestamp Unix timestamp of the anchor creation.
     * @param anchorHash The SHA-256 computed anchor hash.
     */
    function registerAnchor(
        bytes32 merkleRoot,
        bytes32 chainTipHash,
        uint256 sequenceStart,
        uint256 sequenceEnd,
        uint256 eventCount,
        uint256 timestamp,
        bytes32 anchorHash
    ) external onlyOwner {
        require(anchors[anchorHash].timestamp == 0, "Anchor already registered");
        
        anchors[anchorHash] = Anchor({
            merkleRoot: merkleRoot,
            chainTipHash: chainTipHash,
            sequenceStart: sequenceStart,
            sequenceEnd: sequenceEnd,
            eventCount: eventCount,
            timestamp: timestamp,
            anchorHash: anchorHash
        });
        
        emit AnchorRegistered(anchorHash, merkleRoot);
    }
}
