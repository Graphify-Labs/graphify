//+------------------------------------------------------------------+
//|                                                       sample.mq5 |
//+------------------------------------------------------------------+
#property copyright "Sample Author"
#property version   "1.07"
#property strict

#include <Trade\Trade.mqh>
#include "local_helpers.mqh"

enum RiskMode
  {
   RISK_FIXED   = 0,
   RISK_PERCENT = 1
  };

struct SZone
  {
   double            price;
   datetime          created;
   bool              used;
  };

input group "=== GENERAL ==="
input long     magic_number   = 202601;      // Magic number
input RiskMode risk_mode      = RISK_PERCENT;
sinput double  risk_percent   = 0.5;
extern int     max_positions  = 3;

input group "=== VISUAL ==="
input color    box_win_color  = C'20,60,20';
input datetime session_start  = D'2024.01.31 22:00';

CTrade Trade;
SZone  zones[64];

int OnInit()
  {
   Trade.SetExpertMagicNumber(magic_number);
   return(INIT_SUCCEEDED);
  }

double LotSize(double sl_distance)
  {
   if(risk_mode == RISK_FIXED)
      return(1.0);
   double risk = AccountInfoDouble(ACCOUNT_EQUITY) * risk_percent / 100.0;
   return(risk / sl_distance);
  }

bool CanOpen() { return(PositionsTotal() < max_positions); }

void OnTick()
  {
   if(!CanOpen())
      return;
   double lots = LotSize(10.0);
   Trade.Buy(lots);
  }
