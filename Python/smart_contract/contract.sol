// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract FSMViolationAuditor {
    // FSM States as defined in your visualizer
    enum FsmState { START, ADVIEW_SET, LOADED, IMPRESSION, ENGAGEMENT, DISPLAYED }

    struct AppStatus {
        FsmState currentState;
        bool hasViolation;
        string[] methodHistory;
    }

    mapping(string => AppStatus) private appRegistry;
    string[] public appNames;
    mapping(string => bool) private appExists;

    event ViolationDetected(string packageName, string method, string expectedState);

    function recordTransition(string memory _pkg, string memory _method) public {
        if (!appExists[_pkg]) {
            appNames.push(_pkg);
            appExists[_pkg] = true;
            appRegistry[_pkg].currentState = FsmState.START;
        }

        AppStatus storage app = appRegistry[_pkg];
        app.methodHistory.push(_method);

        // Validation Logic
        bool valid = validate(_pkg, _method);
        
        if (!valid) {
            app.hasViolation = true;
            emit ViolationDetected(_pkg, _method, "Sequence Break");
        }
    }

    function validate(string memory _pkg, string memory _method) internal returns (bool) {
        FsmState current = appRegistry[_pkg].currentState;
        bytes32 m = keccak256(abi.encodePacked(_method));

        // 1. ATTACH INFO -> ADVIEW_SET
        if (m == keccak256("attachInfo")) {
            if (current == FsmState.START || current == FsmState.ADVIEW_SET) {
                appRegistry[_pkg].currentState = FsmState.ADVIEW_SET;
                return true;
            }
        }
        // 2. BUILD -> LOADED
        else if (m == keccak256("build")) {
            if (current == FsmState.ADVIEW_SET || current == FsmState.LOADED) {
                appRegistry[_pkg].currentState = FsmState.LOADED;
                return true;
            }
        }
        // 3. ON AD LOADED -> IMPRESSION
        else if (m == keccak256("onAdLoaded")) {
            if (current == FsmState.LOADED || current == FsmState.IMPRESSION) {
                appRegistry[_pkg].currentState = FsmState.IMPRESSION;
                return true;
            }
        }
        // 4. ON AD CLICKED -> ENGAGEMENT
        else if (m == keccak256("onAdClicked")) {
            if (current == FsmState.IMPRESSION || current == FsmState.ENGAGEMENT) {
                appRegistry[_pkg].currentState = FsmState.ENGAGEMENT;
                return true;
            }
        }
        // 5. SHOW -> DISPLAYED
        else if (m == keccak256("show")) {
            if (current == FsmState.ENGAGEMENT || current == FsmState.DISPLAYED) {
                appRegistry[_pkg].currentState = FsmState.DISPLAYED;
                return true;
            }
        }

        return false; // Any other transition is a violation
    }

    function getViolationStatus(string memory _pkg) public view returns (bool) {
        return appRegistry[_pkg].hasViolation;
    }

    function getAllApps() public view returns (string[] memory) {
        return appNames;
    }

    function getAppMethods(string memory _pkg) public view returns (string[] memory) {
        return appRegistry[_pkg].methodHistory;
    }
}
