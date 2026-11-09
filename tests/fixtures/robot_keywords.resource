*** Settings ***
Documentation     Fixture resource for the Robot Framework extractor tests.
Library           RequestsLibrary

*** Keywords ***
Open Session
    Log    opening

Close All Sessions
    Log    closing

Login As Admin
    Open Session
    Log    admin

Login As User
    [Arguments]    ${user}
    Open Session
    Log    ${user}
