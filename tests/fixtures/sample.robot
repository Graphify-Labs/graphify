*** Settings ***
Documentation     Fixture suite for the Robot Framework extractor tests.
Resource          robot_keywords.resource
Library           SeleniumLibrary
Library           Collections
Library           ./sample.py
Library           ${CURDIR}/sample.py    WITH NAME    CurdirLib
Variables         ${UNRESOLVED_VAR}/vars.py
Suite Setup       Prepare Environment
Suite Teardown    Close All Sessions

*** Variables ***
${TARGET}         demo

*** Test Cases ***
Login Works
    [Setup]    Open Session
    Login As Admin
    Should Be Equal    ${TARGET}    demo
    [Teardown]    Close All Sessions

Retry Loop Case
    FOR    ${i}    IN RANGE    3
        Open Session
    END

Data Driven Case
    [Template]    Login As User
    alice
    bob

*** Keywords ***
Prepare Environment
    Log    preparing
    Open Session
