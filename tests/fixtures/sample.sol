// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IProcessor} from "./IProcessor.sol";

interface IRegistry {
    function ownerOf(uint256 id) external view returns (address);
}

contract Graph is IProcessor {
    IRegistry public registry;

    struct Node {
        uint256 id;
        address owner;
    }

    enum Status {
        Pending,
        Done
    }

    event NodeAdded(uint256 indexed id, address indexed owner);

    modifier onlyOwner(uint256 id) {
        require(_isOwner(id), "not owner");
        _;
    }

    constructor(address _registry) {
        registry = IRegistry(_registry);
    }

    function _isOwner(uint256 id) internal view returns (bool) {
        return registry.ownerOf(id) == msg.sender;
    }

    function addNode(uint256 id) external onlyOwner(id) {
        emit NodeAdded(id, msg.sender);
    }

    function run() external override {
        _isOwner(0);
    }
}
