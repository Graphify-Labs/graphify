// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./solidity/Base.sol";
import {IERC20} from "./solidity/interfaces/IERC20.sol";

interface IToken {
    function mint(address to, uint256 amount) external;
}

library SafeMath {
    function add(uint256 a, uint256 b) internal pure returns (uint256) {
        return a + b;
    }
}

struct Point {
    uint256 x;
    uint256 y;
}

enum Status {
    Active,
    Inactive
}

contract Token is Base, IToken {
    event Transfer(address indexed from, address indexed to, uint256 value);
    error InsufficientBalance(uint256 available, uint256 required);

    using SafeMath for uint256;

    IERC20 public underlying;
    mapping(address => uint256) public balances;
    Status public status;

    constructor(IERC20 token_) {
        underlying = token_;
        status = Status.Active;
    }

    modifier whenActive() {
        require(status == Status.Active, "inactive");
        _;
    }

    function mint(address to, uint256 amount) external onlyOwner whenActive {
        balances[to] = SafeMath.add(balances[to], amount);
        emit Transfer(msg.sender, to, amount);
    }

    function transfer(address to, uint256 amount) public whenActive returns (bool) {
        require(to != address(0), "zero address");
        balances[msg.sender] -= amount;
        balances[to] = SafeMath.add(balances[to], amount);
        underlying.transfer(to, amount);
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function deployChild() public returns (Token) {
        return new Token(underlying);
    }

    receive() external payable {}

    fallback() external {}
}
