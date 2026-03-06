// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract FSMViolationAuditor {
    struct AppStatus {
        string lastState;
        bool hasViolation;
        string[] methodHistory;
    }

    mapping(string => AppStatus) private appRegistry;
    string[] public appNames;
    mapping(string => bool) private appExists;

    function recordTransition(string memory _pkg, string memory _method) public {
        if (!appExists[_pkg]) {
            appNames.push(_pkg);
            appExists[_pkg] = true;
            appRegistry[_pkg].lastState = "START";
        }

        appRegistry[_pkg].methodHistory.push(_method);
        
        // Basic sequence check
        bool valid = validate(_pkg, _method);
        if (!valid) {
            appRegistry[_pkg].hasViolation = true;
        }
    }

    function validate(string memory _pkg, string memory _m) internal returns (bool) {
        string memory current = appRegistry[_pkg].lastState;
        bytes32 curH = keccak256(abi.encodePacked(current));
        bytes32 mH = keccak256(abi.encodePacked(_m));

        // Allow repeating current state
        if (mH == keccak256("attachInfo") && curH == keccak256("ADVIEW_SET")) return true;

        // Transitions
        if (mH == keccak256("attachInfo") && curH == keccak256("START")) {
            appRegistry[_pkg].lastState = "ADVIEW_SET";
            return true;
        }
        if (mH == keccak256("build") && curH == keccak256("ADVIEW_SET")) {
            appRegistry[_pkg].lastState = "LOADED";
            return true;
        }

        return false;
    }

    function getAllApps() public view returns (string[] memory) {
        return appNames;
    }

    function getAppMethods(string memory _pkg) public view returns (string[] memory) {
        return appRegistry[_pkg].methodHistory;
    }
}
