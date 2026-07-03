//+------------------------------------------------------------------+
//|                                                      ICT_Bot.mq5 |
//|                        ICT Sequential Entry Model Expert Advisor  |
//|                                                                    |
//| Replicates the Python ICT trading bot logic identically.          |
//| Modules replicated:                                                |
//|   - entry_model.py  (state machine)                               |
//|   - market_structure.py (swing detection, MSS detection)          |
//|   - liquidity.py (equal levels, liquidity sweeps)                 |
//|   - fvg.py (Fair Value Gap detection, iFVG)                       |
//|   - order_blocks.py (Order Block identification)                  |
//|   - ote.py (Optimal Trade Entry zones)                            |
//|   - premium_discount.py (premium/discount filter)                 |
//|   - kill_zones.py (session time windows in ET)                    |
//|   - risk_management.py (position sizing, daily loss limit)        |
//|   - backtester.py (HTF bias from daily candles)                   |
//+------------------------------------------------------------------+
#property copyright "ICT Bot"
#property link      ""
#property version   "1.00"
#property strict
#property description "ICT Sequential Entry Model - MQL5 Expert Advisor"
#property description "Replicates Python ICT bot logic for Strategy Tester"

//+------------------------------------------------------------------+
//| Input Parameters                                                   |
//| Corresponds to: config/settings.yaml and EntryModel.__init__()    |
//+------------------------------------------------------------------+
input double   RiskPercent       = 0.01;     // Risk per trade (1%)
input double   MaxDailyLoss     = 0.03;     // Max daily loss (3%)
input int      SwingLookback    = 5;        // Swing detection lookback
input double   EqualLevelTolerance = 5.0;   // Equal level tolerance (points)
input double   MinSweepPips     = 2.0;      // Min sweep distance (points)
input int      MaxBufferSize    = 500;      // Max candle buffer size
input double   ContractSize     = 1.0;      // Contract size for position sizing
input double   VolumeMin        = 0.01;     // Minimum volume
input double   VolumeMax        = 100.0;    // Maximum volume
input double   VolumeStep       = 0.01;     // Volume step
input int      HTFLookback      = 5;        // HTF daily candles for bias (5 = tighter recent range matching Python's effective behavior)
input int      HTFSwingLookback = 2;        // HTF swing detection lookback
input double   SLBuffer         = 1.0;      // SL buffer beyond FVG candle (points)
input int      ServerUTCOffset  = 3;        // Broker server UTC offset in hours (-1 = auto-detect via TimeGMTOffset; 3 = Fusion Markets summer/UTC+3)
input bool     DebugMode        = true;      // Enable verbose debug logging

//+------------------------------------------------------------------+
//| Enumerations                                                       |
//| Corresponds to: entry_model.py EntryState enum                    |
//+------------------------------------------------------------------+
enum ENUM_ENTRY_STATE
{
   STATE_WAITING_FOR_SWEEP = 0,   // Waiting for liquidity sweep
   STATE_WAITING_FOR_MSS   = 1,   // Waiting for Market Structure Shift
   STATE_WAITING_FOR_FVG   = 2,   // Waiting for Fair Value Gap
   STATE_READY_TO_ENTER    = 3    // Ready to place entry order
};

enum ENUM_SWEEP_TYPE
{
   SWEEP_NONE = 0,
   SWEEP_HIGH = 1,    // Sweep above equal highs
   SWEEP_LOW  = 2     // Sweep below equal lows
};

enum ENUM_MSS_TYPE
{
   MSS_NONE    = 0,
   MSS_BULLISH = 1,   // Bullish MSS (price breaks above swing high after lower highs)
   MSS_BEARISH = 2    // Bearish MSS (price breaks below swing low after higher lows)
};

enum ENUM_FVG_TYPE
{
   FVG_NONE    = 0,
   FVG_BULLISH = 1,   // Bullish FVG (candle1_high < candle3_low)
   FVG_BEARISH = 2    // Bearish FVG (candle1_low > candle3_high)
};

//+------------------------------------------------------------------+
//| Structures                                                         |
//+------------------------------------------------------------------+

// Candle data structure for the buffer
struct CandleData
{
   datetime time;
   double   open;
   double   high;
   double   low;
   double   close;
};

// Swing point structure
// Corresponds to: market_structure.py detect_swing_points() return value
struct SwingPoint
{
   bool     is_high;    // true = swing_high, false = swing_low
   int      index;      // index in buffer
   double   price;      // high or low price
   datetime time;       // candle timestamp
};

// Equal level structure
// Corresponds to: liquidity.py detect_equal_levels() return value
struct EqualLevel
{
   bool     is_high;       // true = equal_highs, false = equal_lows
   double   level;         // average price level
   int      indices[];     // bar indices forming the level
   int      count;         // number of touches
   int      last_index;    // max of indices (start looking after this)
};

// Sweep info structure
// Corresponds to: liquidity.py detect_liquidity_sweep() return value
struct SweepInfo
{
   ENUM_SWEEP_TYPE type;
   double   level;         // liquidity level that was swept
   int      sweep_index;   // index of sweep candle in buffer
   double   sweep_price;   // extreme price during sweep
   double   close_price;   // close of sweep candle
};

// MSS info structure
// Corresponds to: market_structure.py detect_mss() return value
struct MSSInfo
{
   ENUM_MSS_TYPE type;
   int      break_index;   // index where break occurred
   double   broken_level;  // price level that was broken
   int      swing_index;   // index of the swing point broken
};

// FVG info structure
// Corresponds to: fvg.py detect_fvg() return value
struct FVGInfo
{
   ENUM_FVG_TYPE type;
   double   high;          // upper boundary of gap
   double   low;           // lower boundary of gap
   double   midpoint;      // 50% level for limit entry
   int      index;         // index of middle candle (candle 2)
};

// Order Block structure
// Corresponds to: order_blocks.py find_order_blocks() return value
struct OrderBlock
{
   bool     is_bullish;    // true = bullish_ob, false = bearish_ob
   int      index;         // index of OB candle
   double   high;          // high of OB candle
   double   low;           // low of OB candle
   double   ob_open;       // open of OB candle
   double   ob_close;      // close of OB candle
   bool     mitigated;     // whether OB has been mitigated
};

// Entry signal structure
// Corresponds to: entry_model.py generate_entry_signal() return value
struct EntrySignal
{
   bool     valid;
   string   direction;     // "long" or "short"
   double   entry_price;   // FVG midpoint
   double   stop_loss;
   double   take_profit;
   double   risk_reward;
   bool     ote_confluence;
   bool     ob_confluence;
   string   kill_zone_name;
};

//+------------------------------------------------------------------+
//| Global Variables                                                    |
//+------------------------------------------------------------------+

// State machine state
// Corresponds to: entry_model.py EntryModel.state
ENUM_ENTRY_STATE g_state = STATE_WAITING_FOR_SWEEP;

// Candle buffer (replaces Python list self.candle_buffer)
CandleData g_buffer[];
int        g_buffer_count = 0;

// Detected confirmations
SweepInfo  g_sweep_info;
bool       g_sweep_valid = false;
MSSInfo    g_mss_info;
bool       g_mss_valid = false;
FVGInfo    g_fvg_info;
bool       g_fvg_valid = false;

// HTF range for premium/discount filter
// Corresponds to: entry_model.py self.htf_swing_high, self.htf_swing_low
double     g_htf_swing_high = 0.0;
double     g_htf_swing_low  = 0.0;
bool       g_htf_range_valid = false;

// Daily loss tracking
// Corresponds to: backtester.py daily_pnl, current_day
double     g_daily_pnl = 0.0;
int        g_current_day = 0;  // day of year for tracking daily reset
double     g_day_start_balance = 0.0;

// Last processed bar time (to avoid duplicate processing)
datetime   g_last_bar_time = 0;

// Bar counter for verbose debug in first 100 bars
int        g_bar_counter = 0;

// Track if we have an active pending order or position
bool       g_has_active_trade = false;

// Track the previous kill zone name for stale order cancellation
// When transitioning to a DIFFERENT kill zone, cancel pending orders from prior zone
string     g_previous_kill_zone = "";

//+------------------------------------------------------------------+
//| Kill Zone Time Windows (ET/Eastern Time)                           |
//| Corresponds to: kill_zones.py KILL_ZONES dict                     |
//|                                                                    |
//| Asian:  20:00 - 00:00 ET (crosses midnight)                       |
//| London: 02:00 - 05:00 ET                                          |
//| NY AM:  10:00 - 11:00 ET                                          |
//| NY PM:  13:30 - 16:00 ET                                          |
//|                                                                    |
//| Note: MT5 server time is used. The UTC offset for ET is applied   |
//| to convert. ET = UTC-5 (EST) or UTC-4 (EDT).                      |
//| We compute the offset dynamically based on DST rules.             |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Get ET offset from UTC in hours                                    |
//| US Eastern: UTC-5 standard, UTC-4 daylight                        |
//| DST: 2nd Sunday March to 1st Sunday November                      |
//+------------------------------------------------------------------+
int GetETOffsetHours(datetime dt)
{
   MqlDateTime mdt;
   TimeToStruct(dt, mdt);

   int month = mdt.mon;
   int day   = mdt.day;
   int dow   = mdt.day_of_week; // 0=Sunday

   // January, February: EST (UTC-5)
   if(month < 3) return -5;
   // April to October: EDT (UTC-4)
   if(month > 3 && month < 11) return -4;
   // November: check if before first Sunday
   if(month == 11)
   {
      // First Sunday: find it
      int first_sunday = 1 + ((7 - ((dow - (day - 1) % 7 + 7) % 7)) % 7);
      // Simplified: day <= first Sunday means still EDT
      // Actually: on the first Sunday at 2am, clocks fall back
      // For simplicity, if day < first Sunday -> EDT, else EST
      // Calculate first Sunday of November
      MqlDateTime nov1;
      TimeToStruct(dt, nov1);
      nov1.day = 1;
      datetime nov1_dt = StructToTime(nov1);
      MqlDateTime nov1_struct;
      TimeToStruct(nov1_dt, nov1_struct);
      int nov1_dow = nov1_struct.day_of_week;
      int fs = (nov1_dow == 0) ? 1 : (8 - nov1_dow);
      if(day < fs) return -4;
      return -5;
   }
   // March: check if after second Sunday
   if(month == 3)
   {
      MqlDateTime mar1;
      TimeToStruct(dt, mar1);
      mar1.day = 1;
      datetime mar1_dt = StructToTime(mar1);
      MqlDateTime mar1_struct;
      TimeToStruct(mar1_dt, mar1_struct);
      int mar1_dow = mar1_struct.day_of_week;
      int first_sun = (mar1_dow == 0) ? 1 : (8 - mar1_dow);
      int second_sun = first_sun + 7;
      if(day >= second_sun) return -4;
      return -5;
   }

   return -5; // default EST
}

//+------------------------------------------------------------------+
//| Get the broker server UTC offset in seconds                        |
//| Uses TimeGMTOffset() for auto-detection, falls back to manual      |
//| ServerUTCOffset input when auto-detect is disabled (-1 is auto).   |
//|                                                                    |
//| TimeGMTOffset() returns the difference in seconds between the      |
//| broker's server time and GMT. So:                                  |
//|   UTC_time = server_time - TimeGMTOffset()                         |
//|                                                                    |
//| For Fusion Markets (UTC+2 winter / UTC+3 summer DST):              |
//|   TimeGMTOffset() would return 7200 (winter) or 10800 (summer)    |
//+------------------------------------------------------------------+
int GetBrokerUTCOffsetSeconds()
{
   // In Strategy Tester, TimeGMTOffset() ALWAYS returns 0 (known MT5 limitation).
   // We must use the manual ServerUTCOffset when running in tester mode.
   if(MQLInfoInteger(MQL_TESTER))
   {
      // In tester: always use manual offset (never trust TimeGMTOffset which is 0)
      if(ServerUTCOffset == -1)
      {
         Print("ICT Bot WARNING: Running in Strategy Tester with ServerUTCOffset=-1 (auto).",
               " TimeGMTOffset() returns 0 in tester! Using 0. Set ServerUTCOffset manually!");
         return 0;
      }
      return ServerUTCOffset * 3600;
   }
   
   if(ServerUTCOffset == -1)
   {
      // Auto-detect: TimeGMTOffset() returns broker's offset from GMT in seconds
      return (int)TimeGMTOffset();
   }
   else
   {
      // Manual override: convert hours to seconds
      return ServerUTCOffset * 3600;
   }
}

//+------------------------------------------------------------------+
//| Convert server time to ET hour and minute                          |
//| Corresponds to: kill_zones.py _to_et()                            |
//|                                                                    |
//| Flow: server_time -> UTC -> ET                                     |
//| Step 1: UTC = server_time - broker_utc_offset                      |
//| Step 2: ET = UTC + ET_offset (where ET_offset is -5 or -4)        |
//|                                                                    |
//| The Python backtester's tick data is in UTC (time_msc is epoch =  |
//| UTC). Python kill_zones.py converts UTC -> ET using zoneinfo.     |
//| For MQL5 to match, we must correctly convert:                      |
//|   broker server time -> UTC -> ET                                  |
//+------------------------------------------------------------------+
void ServerTimeToET(datetime server_time, int &et_hour, int &et_minute)
{
   // Step 1: Convert server time to UTC
   int broker_offset_sec = GetBrokerUTCOffsetSeconds();
   datetime utc_time = server_time - broker_offset_sec;
   
   // Step 2: Get ET offset for this UTC time (handles US DST)
   int et_offset = GetETOffsetHours(utc_time);
   
   // Step 3: Apply ET offset to UTC
   MqlDateTime mdt;
   TimeToStruct(utc_time, mdt);
   
   int total_minutes = mdt.hour * 60 + mdt.min + et_offset * 60;
   
   // Handle day wrapping
   if(total_minutes < 0) total_minutes += 1440;
   if(total_minutes >= 1440) total_minutes -= 1440;
   
   et_hour   = total_minutes / 60;
   et_minute = total_minutes % 60;
}

//+------------------------------------------------------------------+
//| Check if current time is in a kill zone                            |
//| Corresponds to: kill_zones.py is_in_kill_zone()                   |
//| Returns: kill zone name or "" if not in any KZ                    |
//+------------------------------------------------------------------+
string GetActiveKillZone(datetime server_time)
{
   int et_hour, et_minute;
   ServerTimeToET(server_time, et_hour, et_minute);
   int et_total = et_hour * 60 + et_minute;
   
   string result = "";
   
   // Asian: 20:00 - 00:00 ET (crosses midnight)
   // Note: After wrapping in ServerTimeToET, et_total is always in [0, 1439].
   // The Python time comparison uses time(0,0) as end which excludes midnight
   // exactly. The condition et_total >= 1200 covers 20:00-23:59 ET, which is
   // functionally identical to the Python behavior (00:00:00 is never matched).
   if(et_total >= 1200)
      result = "asian";
   
   // London: 02:00 - 05:00 ET
   else if(et_total >= 120 && et_total < 300)
      result = "london";
   
   // NY AM: 10:00 - 11:00 ET
   else if(et_total >= 600 && et_total < 660)
      result = "ny_am";
   
   // NY PM: 13:30 - 16:00 ET
   else if(et_total >= 810 && et_total < 960)
      result = "ny_pm";
   
   // Debug: log the ET time and kill zone determination periodically
   // Only log on the first candle of each minute to reduce spam
   static datetime last_debug_time = 0;
   if(DebugMode && server_time != last_debug_time)
   {
      last_debug_time = server_time;
      int broker_offset_sec = GetBrokerUTCOffsetSeconds();
      if(result != "")
      {
         Print("ICT Debug: ServerTime=", TimeToString(server_time, TIME_DATE|TIME_MINUTES),
               " -> ET ", StringFormat("%02d:%02d", et_hour, et_minute),
               " | KillZone=", result,
               " | BrokerOffset=", broker_offset_sec/3600, "h",
               " | AutoDetect=", (ServerUTCOffset == -1 ? "Yes" : "No"));
      }
   }
   
   return result;
}

//+------------------------------------------------------------------+
//| Cancel all unfilled pending orders for this EA                     |
//| Corresponds to: Python backtester has no pending order concept;   |
//| it sets active_trade immediately. This ensures the live EA does   |
//| not accumulate stale limit orders from prior kill zones, keeping  |
//| behavior consistent with the Python model.                        |
//+------------------------------------------------------------------+
void CancelPendingOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0 && OrderSelect(ticket))
      {
         if(OrderGetString(ORDER_SYMBOL) == _Symbol
            && OrderGetInteger(ORDER_MAGIC) == 20240101)
         {
            MqlTradeRequest request;
            MqlTradeResult  result;
            ZeroMemory(request);
            ZeroMemory(result);
            request.action = TRADE_ACTION_REMOVE;
            request.order  = ticket;
            OrderSend(request, result);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Reset the entry model state                                        |
//| Corresponds to: entry_model.py EntryModel.reset()                 |
//+------------------------------------------------------------------+
void ResetEntryModel()
{
   if(DebugMode && g_state != STATE_WAITING_FOR_SWEEP && g_buffer_count > 0)
   {
      Print("ICT Debug: [RESET] Entry model reset",
            " | PrevState=", EnumToString(g_state),
            " | BufferWas=", g_buffer_count);
   }
   
   g_state = STATE_WAITING_FOR_SWEEP;
   g_buffer_count = 0;
   ArrayResize(g_buffer, 0);
   g_sweep_valid = false;
   g_mss_valid   = false;
   g_fvg_valid   = false;
   
   // NOTE: We do NOT call CancelPendingOrders() here.
   // Previously this was called on every reset which would cancel orders
   // that were JUST placed (since ProcessNewCandle calls ResetEntryModel
   // after PlaceLimitOrder). Stale orders are now cancelled only when
   // transitioning to a DIFFERENT kill zone - see CheckForNewBar().
}

//+------------------------------------------------------------------+
//| Add candle to buffer                                               |
//| Corresponds to: entry_model.py EntryModel.update() buffer logic   |
//+------------------------------------------------------------------+
void AddCandleToBuffer(const CandleData &candle)
{
   g_buffer_count++;
   ArrayResize(g_buffer, g_buffer_count);
   g_buffer[g_buffer_count - 1] = candle;
   
   // Cap buffer to MaxBufferSize (discard oldest)
   // Corresponds to: entry_model.py self.candle_buffer[-self.max_buffer_size:]
   if(g_buffer_count > MaxBufferSize)
   {
      int excess = g_buffer_count - MaxBufferSize;
      CandleData temp[];
      ArrayResize(temp, MaxBufferSize);
      for(int i = 0; i < MaxBufferSize; i++)
         temp[i] = g_buffer[i + excess];
      ArrayResize(g_buffer, MaxBufferSize);
      for(int i = 0; i < MaxBufferSize; i++)
         g_buffer[i] = temp[i];
      g_buffer_count = MaxBufferSize;
      
      // Adjust stored indices after trimming
      if(g_sweep_valid)
         g_sweep_info.sweep_index -= excess;
      if(g_mss_valid)
      {
         g_mss_info.break_index -= excess;
         g_mss_info.swing_index -= excess;
      }
      if(g_fvg_valid)
         g_fvg_info.index -= excess;
      
      // Guard: reset state if any stored index went negative
      // (the referenced candle was trimmed from the buffer)
      // This matches Python behavior where buffer slicing discards
      // indices entirely and detection re-scans from scratch.
      if(g_sweep_valid && g_sweep_info.sweep_index < 0)
      {
         g_sweep_valid = false;
         g_state = STATE_WAITING_FOR_SWEEP;
      }
      if(g_mss_valid && (g_mss_info.break_index < 0 || g_mss_info.swing_index < 0))
      {
         g_mss_valid = false;
         g_state = STATE_WAITING_FOR_SWEEP;
      }
      if(g_fvg_valid && g_fvg_info.index < 0)
      {
         g_fvg_valid = false;
         g_state = STATE_WAITING_FOR_SWEEP;
      }
   }
}

//+------------------------------------------------------------------+
//| Detect Swing Points                                                |
//| Corresponds to: market_structure.py detect_swing_points()         |
//|                                                                    |
//| A swing high: high[i] > high[i-j] AND high[i] > high[i+j]        |
//|   for all j in 1..lookback (strict >)                             |
//| A swing low: low[i] < low[i-j] AND low[i] < low[i+j]            |
//|   for all j in 1..lookback (strict <)                             |
//+------------------------------------------------------------------+
int DetectSwingPoints(const CandleData &candles[], int count, int lookback,
                      SwingPoint &swings[], int max_swings = 200)
{
   ArrayResize(swings, max_swings);
   int swing_count = 0;
   
   for(int i = lookback; i < count - lookback; i++)
   {
      // Check for swing high
      bool is_swing_high = true;
      for(int j = 1; j <= lookback; j++)
      {
         if(candles[i].high <= candles[i - j].high || candles[i].high <= candles[i + j].high)
         {
            is_swing_high = false;
            break;
         }
      }
      if(is_swing_high && swing_count < max_swings)
      {
         swings[swing_count].is_high = true;
         swings[swing_count].index   = i;
         swings[swing_count].price   = candles[i].high;
         swings[swing_count].time    = candles[i].time;
         swing_count++;
      }
      
      // Check for swing low
      bool is_swing_low = true;
      for(int j = 1; j <= lookback; j++)
      {
         if(candles[i].low >= candles[i - j].low || candles[i].low >= candles[i + j].low)
         {
            is_swing_low = false;
            break;
         }
      }
      if(is_swing_low && swing_count < max_swings)
      {
         swings[swing_count].is_high = false;
         swings[swing_count].index   = i;
         swings[swing_count].price   = candles[i].low;
         swings[swing_count].time    = candles[i].time;
         swing_count++;
      }
   }
   
   ArrayResize(swings, swing_count);
   return swing_count;
}

//+------------------------------------------------------------------+
//| Detect MSS (Market Structure Shift)                                |
//| Corresponds to: market_structure.py detect_mss()                  |
//|                                                                    |
//| Bullish MSS: swing_high with price LOWER than previous swing_high |
//|   (lower highs = bearish trend), then close > that swing_high     |
//| Bearish MSS: swing_low with price HIGHER than previous swing_low  |
//|   (higher lows = bullish trend), then close < that swing_low      |
//+------------------------------------------------------------------+
int DetectMSS(const CandleData &candles[], int count,
              const SwingPoint &swings[], int swing_count,
              MSSInfo &mss_events[], int max_mss = 50)
{
   ArrayResize(mss_events, max_mss);
   int mss_count = 0;
   
   // Separate swing highs and lows
   SwingPoint swing_highs[];
   SwingPoint swing_lows[];
   int sh_count = 0, sl_count = 0;
   
   ArrayResize(swing_highs, swing_count);
   ArrayResize(swing_lows, swing_count);
   
   for(int i = 0; i < swing_count; i++)
   {
      if(swings[i].is_high)
      {
         swing_highs[sh_count] = swings[i];
         sh_count++;
      }
      else
      {
         swing_lows[sl_count] = swings[i];
         sl_count++;
      }
   }
   ArrayResize(swing_highs, sh_count);
   ArrayResize(swing_lows, sl_count);
   
   // Detect bullish MSS: price breaks above a swing high after bearish trend
   // (current swing_high price < previous swing_high price = lower highs)
   for(int i = 0; i < sh_count; i++)
   {
      if(i > 0)
      {
         // MSS requires current swing high LOWER than previous (bearish trend)
         if(swing_highs[i].price >= swing_highs[i - 1].price)
            continue;
      }
      
      // Find first candle after swing high that closes above it
      for(int bar_idx = swing_highs[i].index + 1; bar_idx < count; bar_idx++)
      {
         if(candles[bar_idx].close > swing_highs[i].price)
         {
            if(mss_count < max_mss)
            {
               mss_events[mss_count].type         = MSS_BULLISH;
               mss_events[mss_count].break_index  = bar_idx;
               mss_events[mss_count].broken_level = swing_highs[i].price;
               mss_events[mss_count].swing_index  = swing_highs[i].index;
               mss_count++;
            }
            break;
         }
      }
   }
   
   // Detect bearish MSS: price breaks below a swing low after bullish trend
   // (current swing_low price > previous swing_low price = higher lows)
   for(int i = 0; i < sl_count; i++)
   {
      if(i > 0)
      {
         // MSS requires current swing low HIGHER than previous (bullish trend)
         if(swing_lows[i].price <= swing_lows[i - 1].price)
            continue;
      }
      
      // Find first candle after swing low that closes below it
      for(int bar_idx = swing_lows[i].index + 1; bar_idx < count; bar_idx++)
      {
         if(candles[bar_idx].close < swing_lows[i].price)
         {
            if(mss_count < max_mss)
            {
               mss_events[mss_count].type         = MSS_BEARISH;
               mss_events[mss_count].break_index  = bar_idx;
               mss_events[mss_count].broken_level = swing_lows[i].price;
               mss_events[mss_count].swing_index  = swing_lows[i].index;
               mss_count++;
            }
            break;
         }
      }
   }
   
   ArrayResize(mss_events, mss_count);
   return mss_count;
}

//+------------------------------------------------------------------+
//| Detect Equal Levels                                                |
//| Corresponds to: liquidity.py detect_equal_levels()                |
//|   and _group_equal_levels()                                       |
//|                                                                    |
//| Groups highs (or lows) within tolerance_pips of each other.       |
//| Requires >= 2 touches per group.                                  |
//+------------------------------------------------------------------+
int DetectEqualLevels(const CandleData &candles[], int count,
                      double tolerance, EqualLevel &levels[],
                      int max_levels = 50)
{
   ArrayResize(levels, max_levels);
   int level_count = 0;
   
   // --- Equal Highs ---
   bool used_high[];
   ArrayResize(used_high, count);
   ArrayInitialize(used_high, false);
   
   for(int i = 0; i < count && level_count < max_levels; i++)
   {
      if(used_high[i]) continue;
      
      int group[];
      int group_size = 1;
      ArrayResize(group, count);
      group[0] = i;
      
      for(int j = i + 1; j < count; j++)
      {
         if(used_high[j]) continue;
         if(MathAbs(candles[i].high - candles[j].high) <= tolerance)
         {
            group[group_size] = j;
            group_size++;
            used_high[j] = true;
         }
      }
      
      if(group_size >= 2)
      {
         used_high[i] = true;
         double sum = 0;
         int max_idx = 0;
         for(int k = 0; k < group_size; k++)
         {
            sum += candles[group[k]].high;
            if(group[k] > max_idx) max_idx = group[k];
         }
         levels[level_count].is_high    = true;
         levels[level_count].level      = sum / group_size;
         levels[level_count].count      = group_size;
         levels[level_count].last_index = max_idx;
         ArrayResize(levels[level_count].indices, group_size);
         for(int k = 0; k < group_size; k++)
            levels[level_count].indices[k] = group[k];
         level_count++;
      }
   }
   
   // --- Equal Lows ---
   bool used_low[];
   ArrayResize(used_low, count);
   ArrayInitialize(used_low, false);
   
   for(int i = 0; i < count && level_count < max_levels; i++)
   {
      if(used_low[i]) continue;
      
      int group[];
      int group_size = 1;
      ArrayResize(group, count);
      group[0] = i;
      
      for(int j = i + 1; j < count; j++)
      {
         if(used_low[j]) continue;
         if(MathAbs(candles[i].low - candles[j].low) <= tolerance)
         {
            group[group_size] = j;
            group_size++;
            used_low[j] = true;
         }
      }
      
      if(group_size >= 2)
      {
         used_low[i] = true;
         double sum = 0;
         int max_idx = 0;
         for(int k = 0; k < group_size; k++)
         {
            sum += candles[group[k]].low;
            if(group[k] > max_idx) max_idx = group[k];
         }
         levels[level_count].is_high    = false;
         levels[level_count].level      = sum / group_size;
         levels[level_count].count      = group_size;
         levels[level_count].last_index = max_idx;
         ArrayResize(levels[level_count].indices, group_size);
         for(int k = 0; k < group_size; k++)
            levels[level_count].indices[k] = group[k];
         level_count++;
      }
   }
   
   ArrayResize(levels, level_count);
   return level_count;
}

//+------------------------------------------------------------------+
//| Detect Liquidity Sweeps                                            |
//| Corresponds to: liquidity.py detect_liquidity_sweep()             |
//|                                                                    |
//| sweep_high: high > level + min_sweep_pips AND close < level       |
//| sweep_low:  low < level - min_sweep_pips AND close > level        |
//| Only first sweep per level is detected.                           |
//+------------------------------------------------------------------+
int DetectLiquiditySweeps(const CandleData &candles[], int count,
                          const EqualLevel &levels[], int level_count,
                          double min_sweep,
                          SweepInfo &sweeps[], int max_sweeps = 50)
{
   ArrayResize(sweeps, max_sweeps);
   int sweep_count = 0;
   
   for(int lev = 0; lev < level_count && sweep_count < max_sweeps; lev++)
   {
      double level_price = levels[lev].level;
      int start_idx = levels[lev].last_index + 1;
      
      for(int bar_idx = start_idx; bar_idx < count; bar_idx++)
      {
         if(levels[lev].is_high)
         {
            // Sweep above: high exceeds level + min_sweep, close below level
            if(candles[bar_idx].high > level_price + min_sweep
               && candles[bar_idx].close < level_price)
            {
               sweeps[sweep_count].type        = SWEEP_HIGH;
               sweeps[sweep_count].level       = level_price;
               sweeps[sweep_count].sweep_index = bar_idx;
               sweeps[sweep_count].sweep_price = candles[bar_idx].high;
               sweeps[sweep_count].close_price = candles[bar_idx].close;
               sweep_count++;
               break; // Only first sweep per level
            }
         }
         else
         {
            // Sweep below: low exceeds level - min_sweep, close above level
            if(candles[bar_idx].low < level_price - min_sweep
               && candles[bar_idx].close > level_price)
            {
               sweeps[sweep_count].type        = SWEEP_LOW;
               sweeps[sweep_count].level       = level_price;
               sweeps[sweep_count].sweep_index = bar_idx;
               sweeps[sweep_count].sweep_price = candles[bar_idx].low;
               sweeps[sweep_count].close_price = candles[bar_idx].close;
               sweep_count++;
               break; // Only first sweep per level
            }
         }
      }
   }
   
   ArrayResize(sweeps, sweep_count);
   return sweep_count;
}

//+------------------------------------------------------------------+
//| Detect Fair Value Gaps                                              |
//| Corresponds to: fvg.py detect_fvg()                               |
//|                                                                    |
//| Bullish FVG: candle[i-2].high < candle[i].low                     |
//|   gap = [candle[i-2].high, candle[i].low]                         |
//| Bearish FVG: candle[i-2].low > candle[i].high                     |
//|   gap = [candle[i].high, candle[i-2].low]                         |
//| midpoint = (high + low) / 2                                       |
//+------------------------------------------------------------------+
int DetectFVG(const CandleData &candles[], int count,
              FVGInfo &fvgs[], int max_fvgs = 100)
{
   ArrayResize(fvgs, max_fvgs);
   int fvg_count = 0;
   
   for(int i = 2; i < count && fvg_count < max_fvgs; i++)
   {
      double candle1_high = candles[i - 2].high;
      double candle1_low  = candles[i - 2].low;
      double candle3_high = candles[i].high;
      double candle3_low  = candles[i].low;
      
      // Bullish FVG: gap between candle 1 high and candle 3 low
      if(candle1_high < candle3_low)
      {
         double fvg_low  = candle1_high;
         double fvg_high = candle3_low;
         fvgs[fvg_count].type     = FVG_BULLISH;
         fvgs[fvg_count].high     = fvg_high;
         fvgs[fvg_count].low      = fvg_low;
         fvgs[fvg_count].midpoint = (fvg_high + fvg_low) / 2.0;
         fvgs[fvg_count].index    = i - 1; // Middle candle
         fvg_count++;
      }
      
      // Bearish FVG: gap between candle 1 low and candle 3 high
      if(candle1_low > candle3_high)
      {
         double fvg_high = candle1_low;
         double fvg_low  = candle3_high;
         fvgs[fvg_count].type     = FVG_BEARISH;
         fvgs[fvg_count].high     = fvg_high;
         fvgs[fvg_count].low      = fvg_low;
         fvgs[fvg_count].midpoint = (fvg_high + fvg_low) / 2.0;
         fvgs[fvg_count].index    = i - 1; // Middle candle
         fvg_count++;
      }
   }
   
   ArrayResize(fvgs, fvg_count);
   return fvg_count;
}

//+------------------------------------------------------------------+
//| Find Order Blocks                                                  |
//| Corresponds to: order_blocks.py find_order_blocks()               |
//|                                                                    |
//| Bullish OB = last bearish candle (close < open) before bullish    |
//|   structure event                                                  |
//| Bearish OB = last bullish candle (close > open) before bearish    |
//|   structure event                                                  |
//+------------------------------------------------------------------+
int FindOrderBlocks(const CandleData &candles[], int count,
                    const MSSInfo &mss_event,
                    OrderBlock &obs[], int max_obs = 20)
{
   ArrayResize(obs, max_obs);
   int ob_count = 0;
   
   int break_idx = mss_event.break_index;
   
   if(mss_event.type == MSS_BULLISH)
   {
      // Bullish OB: last bearish candle before the break
      for(int i = break_idx - 1; i >= 0; i--)
      {
         if(candles[i].close < candles[i].open) // Bearish candle
         {
            if(ob_count < max_obs)
            {
               obs[ob_count].is_bullish = true;
               obs[ob_count].index      = i;
               obs[ob_count].high       = candles[i].high;
               obs[ob_count].low        = candles[i].low;
               obs[ob_count].ob_open    = candles[i].open;
               obs[ob_count].ob_close   = candles[i].close;
               obs[ob_count].mitigated  = false;
               ob_count++;
            }
            break;
         }
      }
   }
   else if(mss_event.type == MSS_BEARISH)
   {
      // Bearish OB: last bullish candle before the break
      for(int i = break_idx - 1; i >= 0; i--)
      {
         if(candles[i].close > candles[i].open) // Bullish candle
         {
            if(ob_count < max_obs)
            {
               obs[ob_count].is_bullish = false;
               obs[ob_count].index      = i;
               obs[ob_count].high       = candles[i].high;
               obs[ob_count].low        = candles[i].low;
               obs[ob_count].ob_open    = candles[i].open;
               obs[ob_count].ob_close   = candles[i].close;
               obs[ob_count].mitigated  = false;
               ob_count++;
            }
            break;
         }
      }
   }
   
   ArrayResize(obs, ob_count);
   return ob_count;
}

//+------------------------------------------------------------------+
//| Calculate OTE Zone                                                 |
//| Corresponds to: ote.py calculate_ote_zone()                       |
//|                                                                    |
//| Bullish OTE: [swing_low + (1-0.79)*range, swing_low + (1-0.62)*range] |
//| Bearish OTE: [swing_low + 0.62*range, swing_low + 0.79*range]    |
//+------------------------------------------------------------------+
void CalculateOTEZone(double swing_high, double swing_low, string direction,
                      double &ote_low, double &ote_high)
{
   double price_range = swing_high - swing_low;
   
   if(direction == "bullish")
   {
      // Bullish: pullback zone from low
      ote_low  = swing_low + (1.0 - 0.79) * price_range; // 0.21 * range
      ote_high = swing_low + (1.0 - 0.62) * price_range; // 0.38 * range
   }
   else // bearish
   {
      // Bearish: pullback zone from high
      ote_low  = swing_low + 0.62 * price_range;
      ote_high = swing_low + 0.79 * price_range;
   }
}

//+------------------------------------------------------------------+
//| Check if price is in OTE zone                                      |
//| Corresponds to: ote.py is_price_in_ote()                          |
//+------------------------------------------------------------------+
bool IsPriceInOTE(double price, double ote_low, double ote_high)
{
   return (price >= ote_low && price <= ote_high);
}

//+------------------------------------------------------------------+
//| Premium/Discount Filter                                            |
//| Corresponds to: premium_discount.py                               |
//|                                                                    |
//| equilibrium = (swing_high + swing_low) / 2                        |
//| is_premium: price > equilibrium                                   |
//| is_discount: price < equilibrium                                  |
//+------------------------------------------------------------------+
double CalculateEquilibrium(double swing_high, double swing_low)
{
   return (swing_high + swing_low) / 2.0;
}

bool IsPremium(double price, double equilibrium)
{
   return price > equilibrium;
}

bool IsDiscount(double price, double equilibrium)
{
   return price < equilibrium;
}

//+------------------------------------------------------------------+
//| Check Liquidity Sweep State                                        |
//| Corresponds to: entry_model.py EntryModel.check_liquidity_sweep() |
//|                                                                    |
//| Need >= 10 candles. Detect equal levels, then sweeps.             |
//| Take most recent sweep (sweeps[-1]).                              |
//+------------------------------------------------------------------+
void CheckLiquiditySweep()
{
   if(g_buffer_count < 10)
      return;
   
   EqualLevel levels[];
   int level_count = DetectEqualLevels(g_buffer, g_buffer_count,
                                        EqualLevelTolerance, levels);
   if(level_count == 0)
      return;
   
   SweepInfo sweeps[];
   int sweep_count = DetectLiquiditySweeps(g_buffer, g_buffer_count,
                                            levels, level_count,
                                            MinSweepPips, sweeps);
   if(sweep_count > 0)
   {
      // Take the most recent sweep (last one = sweeps[-1])
      g_sweep_info  = sweeps[sweep_count - 1];
      g_sweep_valid = true;
      g_state       = STATE_WAITING_FOR_MSS;
      
      if(DebugMode)
      {
         string sweep_type_str = (g_sweep_info.type == SWEEP_HIGH) ? "SWEEP_HIGH" : "SWEEP_LOW";
         Print("ICT Debug: [STATE] SWEEP DETECTED -> WAITING_FOR_MSS",
               " | Type=", sweep_type_str,
               " | Level=", DoubleToString(g_sweep_info.level, _Digits),
               " | SweepPrice=", DoubleToString(g_sweep_info.sweep_price, _Digits),
               " | SweepIdx=", g_sweep_info.sweep_index,
               " | BufferSize=", g_buffer_count,
               " | EqualLevels=", level_count,
               " | TotalSweeps=", sweep_count);
      }
   }
}

//+------------------------------------------------------------------+
//| Check MSS State                                                    |
//| Corresponds to: entry_model.py EntryModel.check_mss()            |
//|                                                                    |
//| Need >= lookback*2+1 candles. Detect swing points then MSS.      |
//| Find MSS with break_index > sweep_index.                          |
//| Validate: sweep_high -> bearish_mss; sweep_low -> bullish_mss    |
//+------------------------------------------------------------------+
void CheckMSS()
{
   if(g_buffer_count < SwingLookback * 2 + 1)
      return;
   
   SwingPoint swings[];
   int swing_count = DetectSwingPoints(g_buffer, g_buffer_count,
                                        SwingLookback, swings);
   if(swing_count == 0)
      return;
   
   MSSInfo mss_events[];
   int mss_count = DetectMSS(g_buffer, g_buffer_count,
                              swings, swing_count, mss_events);
   if(mss_count == 0)
      return;
   
   // Find MSS that occurs after the sweep
   int sweep_idx = g_sweep_info.sweep_index;
   
   for(int i = 0; i < mss_count; i++)
   {
      if(mss_events[i].break_index > sweep_idx)
      {
         // Validate MSS direction aligns with sweep direction
         if(g_sweep_info.type == SWEEP_HIGH && mss_events[i].type == MSS_BEARISH)
         {
            g_mss_info  = mss_events[i];
            g_mss_valid = true;
            g_state     = STATE_WAITING_FOR_FVG;
            
            if(DebugMode)
            {
               Print("ICT Debug: [STATE] MSS DETECTED -> WAITING_FOR_FVG",
                     " | Type=BEARISH_MSS",
                     " | BrokenLevel=", DoubleToString(g_mss_info.broken_level, _Digits),
                     " | BreakIdx=", g_mss_info.break_index,
                     " | SwingIdx=", g_mss_info.swing_index,
                     " | After SweepIdx=", sweep_idx);
            }
            break;
         }
         else if(g_sweep_info.type == SWEEP_LOW && mss_events[i].type == MSS_BULLISH)
         {
            g_mss_info  = mss_events[i];
            g_mss_valid = true;
            g_state     = STATE_WAITING_FOR_FVG;
            
            if(DebugMode)
            {
               Print("ICT Debug: [STATE] MSS DETECTED -> WAITING_FOR_FVG",
                     " | Type=BULLISH_MSS",
                     " | BrokenLevel=", DoubleToString(g_mss_info.broken_level, _Digits),
                     " | BreakIdx=", g_mss_info.break_index,
                     " | SwingIdx=", g_mss_info.swing_index,
                     " | After SweepIdx=", sweep_idx);
            }
            break;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check FVG State                                                    |
//| Corresponds to: entry_model.py EntryModel.check_fvg()            |
//|                                                                    |
//| Detect FVGs. Filter by index >= mss_break_index and matching type.|
//| For bearish_fvg: take max by high.                                |
//| For bullish_fvg: take min by low.                                 |
//+------------------------------------------------------------------+
void CheckFVG()
{
   if(g_buffer_count < 3)
      return;
   
   FVGInfo fvgs[];
   int fvg_count = DetectFVG(g_buffer, g_buffer_count, fvgs);
   if(fvg_count == 0)
      return;
   
   int mss_break_idx = g_mss_info.break_index;
   ENUM_FVG_TYPE expected_type = (g_mss_info.type == MSS_BEARISH) ? FVG_BEARISH : FVG_BULLISH;
   
   // Collect valid FVGs (at or after mss_break_index, matching type)
   FVGInfo valid_fvgs[];
   int valid_count = 0;
   ArrayResize(valid_fvgs, fvg_count);
   
   for(int i = 0; i < fvg_count; i++)
   {
      if(fvgs[i].index >= mss_break_idx && fvgs[i].type == expected_type)
      {
         valid_fvgs[valid_count] = fvgs[i];
         valid_count++;
      }
   }
   
   if(valid_count > 0)
   {
      // Select: bearish_fvg -> max by high; bullish_fvg -> min by low
      int best_idx = 0;
      if(expected_type == FVG_BEARISH)
      {
         for(int i = 1; i < valid_count; i++)
            if(valid_fvgs[i].high > valid_fvgs[best_idx].high)
               best_idx = i;
      }
      else // FVG_BULLISH
      {
         for(int i = 1; i < valid_count; i++)
            if(valid_fvgs[i].low < valid_fvgs[best_idx].low)
               best_idx = i;
      }
      
      g_fvg_info  = valid_fvgs[best_idx];
      g_fvg_valid = true;
      g_state     = STATE_READY_TO_ENTER;
      
      if(DebugMode)
      {
         string fvg_type_str = (expected_type == FVG_BEARISH) ? "BEARISH_FVG" : "BULLISH_FVG";
         Print("ICT Debug: [STATE] FVG DETECTED -> READY_TO_ENTER",
               " | Type=", fvg_type_str,
               " | High=", DoubleToString(g_fvg_info.high, _Digits),
               " | Low=", DoubleToString(g_fvg_info.low, _Digits),
               " | Midpoint=", DoubleToString(g_fvg_info.midpoint, _Digits),
               " | FVG_Idx=", g_fvg_info.index,
               " | ValidFVGs=", valid_count,
               " | TotalFVGs=", fvg_count);
      }
   }
}

//+------------------------------------------------------------------+
//| Find Opposing Liquidity for Take Profit                            |
//| Corresponds to: entry_model.py EntryModel._find_opposing_liquidity() |
//|                                                                    |
//| For short: most recent swing_low price                            |
//| For long: most recent swing_high price                            |
//+------------------------------------------------------------------+
double FindOpposingLiquidity(string direction)
{
   SwingPoint swings[];
   int swing_count = DetectSwingPoints(g_buffer, g_buffer_count,
                                        SwingLookback, swings);
   
   if(direction == "short")
   {
      // Look for swing lows
      double last_swing_low = 0;
      bool found = false;
      for(int i = swing_count - 1; i >= 0; i--)
      {
         if(!swings[i].is_high)
         {
            last_swing_low = swings[i].price;
            found = true;
            break;
         }
      }
      if(found) return last_swing_low;
      
      // Fallback: lowest low in buffer
      double min_low = g_buffer[0].low;
      for(int i = 1; i < g_buffer_count; i++)
         if(g_buffer[i].low < min_low) min_low = g_buffer[i].low;
      return min_low;
   }
   else // long
   {
      // Look for swing highs
      double last_swing_high = 0;
      bool found = false;
      for(int i = swing_count - 1; i >= 0; i--)
      {
         if(swings[i].is_high)
         {
            last_swing_high = swings[i].price;
            found = true;
            break;
         }
      }
      if(found) return last_swing_high;
      
      // Fallback: highest high in buffer
      double max_high = g_buffer[0].high;
      for(int i = 1; i < g_buffer_count; i++)
         if(g_buffer[i].high > max_high) max_high = g_buffer[i].high;
      return max_high;
   }
}

//+------------------------------------------------------------------+
//| Generate Entry Signal                                              |
//| Corresponds to: entry_model.py EntryModel.generate_entry_signal() |
//|                                                                    |
//| Direction: bearish_mss -> short; bullish_mss -> long              |
//| Entry: FVG midpoint (limit order)                                 |
//| SL short: high of FVG candle (at fvg_info.index) + SLBuffer      |
//| SL long: low of FVG candle (at fvg_info.index) - SLBuffer        |
//| TP: opposing swing (most recent swing_low for short, swing_high   |
//|     for long)                                                     |
//| Premium/Discount filter: reject long if entry > equilibrium;      |
//|   reject short if entry < equilibrium                             |
//| OTE confluence (non-blocking)                                     |
//| OB confluence (non-blocking)                                      |
//+------------------------------------------------------------------+
bool GenerateEntrySignal(EntrySignal &signal, string kz_name)
{
   if(!g_sweep_valid || !g_mss_valid || !g_fvg_valid)
      return false;
   
   double entry_price = g_fvg_info.midpoint;
   string direction;
   double stop_loss;
   double take_profit;
   
   if(g_mss_info.type == MSS_BEARISH)
   {
      direction = "short";
      // SL above the candle that created the FVG
      int fvg_candle_idx = g_fvg_info.index;
      if(fvg_candle_idx < g_buffer_count)
         stop_loss = g_buffer[fvg_candle_idx].high + SLBuffer;
      else
         stop_loss = g_fvg_info.high + SLBuffer;
      
      take_profit = FindOpposingLiquidity(direction);
   }
   else // MSS_BULLISH
   {
      direction = "long";
      // SL below the candle that created the FVG
      int fvg_candle_idx = g_fvg_info.index;
      if(fvg_candle_idx < g_buffer_count)
         stop_loss = g_buffer[fvg_candle_idx].low - SLBuffer;
      else
         stop_loss = g_fvg_info.low - SLBuffer;
      
      take_profit = FindOpposingLiquidity(direction);
   }
   
   // --- Premium/Discount Filter ---
   // Corresponds to: entry_model.py generate_entry_signal() P/D check
   if(g_htf_range_valid)
   {
      double equilibrium = CalculateEquilibrium(g_htf_swing_high, g_htf_swing_low);
      if(direction == "long" && IsPremium(entry_price, equilibrium))
      {
         if(DebugMode)
            Print("ICT Debug: [REJECTED] Long signal rejected - entry in PREMIUM zone",
                  " | Entry=", DoubleToString(entry_price, _Digits),
                  " | Equilibrium=", DoubleToString(equilibrium, _Digits),
                  " | HTF_High=", DoubleToString(g_htf_swing_high, _Digits),
                  " | HTF_Low=", DoubleToString(g_htf_swing_low, _Digits));
         return false; // Reject long in premium
      }
      if(direction == "short" && IsDiscount(entry_price, equilibrium))
      {
         if(DebugMode)
            Print("ICT Debug: [REJECTED] Short signal rejected - entry in DISCOUNT zone",
                  " | Entry=", DoubleToString(entry_price, _Digits),
                  " | Equilibrium=", DoubleToString(equilibrium, _Digits),
                  " | HTF_High=", DoubleToString(g_htf_swing_high, _Digits),
                  " | HTF_Low=", DoubleToString(g_htf_swing_low, _Digits));
         return false; // Reject short in discount
      }
   }
   
   // --- OTE Confluence (non-blocking) ---
   bool ote_confluence = false;
   SwingPoint swings[];
   int swing_count = DetectSwingPoints(g_buffer, g_buffer_count, SwingLookback, swings);
   if(swing_count > 0)
   {
      double recent_high = 0, recent_low = 0;
      bool found_high = false, found_low = false;
      for(int i = swing_count - 1; i >= 0; i--)
      {
         if(swings[i].is_high && !found_high) { recent_high = swings[i].price; found_high = true; }
         if(!swings[i].is_high && !found_low) { recent_low = swings[i].price; found_low = true; }
         if(found_high && found_low) break;
      }
      if(found_high && found_low)
      {
         string ote_dir = (direction == "long") ? "bullish" : "bearish";
         double ote_low, ote_high;
         CalculateOTEZone(recent_high, recent_low, ote_dir, ote_low, ote_high);
         ote_confluence = IsPriceInOTE(entry_price, ote_low, ote_high);
      }
   }
   
   // --- Order Block Confluence (non-blocking) ---
   bool ob_confluence = false;
   OrderBlock obs[];
   int ob_count = FindOrderBlocks(g_buffer, g_buffer_count, g_mss_info, obs);
   if(ob_count > 0)
   {
      bool expected_bullish_ob = (direction == "long");
      for(int i = 0; i < ob_count; i++)
      {
         if(obs[i].is_bullish == expected_bullish_ob)
         {
            if(entry_price >= obs[i].low && entry_price <= obs[i].high)
            {
               ob_confluence = true;
               break;
            }
         }
      }
   }
   
   // Calculate risk/reward
   double risk   = MathAbs(entry_price - stop_loss);
   double reward = MathAbs(take_profit - entry_price);
   double rr     = (risk > 0) ? reward / risk : 0.0;
   
   // Fill signal structure
   signal.valid           = true;
   signal.direction       = direction;
   signal.entry_price     = entry_price;
   signal.stop_loss       = stop_loss;
   signal.take_profit     = take_profit;
   signal.risk_reward     = rr;
   signal.ote_confluence  = ote_confluence;
   signal.ob_confluence   = ob_confluence;
   signal.kill_zone_name  = kz_name;
   
   return true;
}

//+------------------------------------------------------------------+
//| Position Sizing                                                    |
//| Corresponds to: risk_management.py calculate_position_size()      |
//|                                                                    |
//| volume = (balance * risk_percent) / (sl_distance * contract_size) |
//| Round to volume_step, clamp to [volume_min, volume_max]           |
//| Skip if volume < volume_min                                       |
//+------------------------------------------------------------------+
double CalculatePositionSize(double balance, double entry_price, double stop_loss_price)
{
   if(balance <= 0) return 0.0;
   
   double sl_distance = MathAbs(entry_price - stop_loss_price);
   if(sl_distance == 0) return 0.0;
   
   double risk_amount = balance * RiskPercent;
   double volume = risk_amount / (sl_distance * ContractSize);
   
   // Round to volume step
   if(VolumeStep > 0)
      volume = MathRound(volume / VolumeStep) * VolumeStep;
   
   // Normalize precision
   volume = NormalizeDouble(volume, 2);
   
   // Clamp
   if(volume < VolumeMin)
      return 0.0; // Skip trade - below minimum
   if(volume > VolumeMax)
      volume = VolumeMax;
   
   return volume;
}

//+------------------------------------------------------------------+
//| Daily Loss Check                                                   |
//| Corresponds to: risk_management.py check_daily_loss_limit()       |
//| and backtester.py daily loss logic                                |
//|                                                                    |
//| if abs(min(daily_pnl, 0)) >= balance * max_daily_loss -> stop     |
//+------------------------------------------------------------------+
bool IsDailyLossLimitReached()
{
   double max_loss = g_day_start_balance * MaxDailyLoss;
   double current_loss = MathAbs(MathMin(g_daily_pnl, 0.0));
   return (current_loss >= max_loss);
}

//+------------------------------------------------------------------+
//| Update HTF Range (Daily timeframe bias)                            |
//| Corresponds to: backtester.py update_htf_range()                  |
//|                                                                    |
//| Fetch 20 D1 candles, detect swing points with lookback=2,         |
//| set HTF range: htf_high = max of all swing_high prices;           |
//|                htf_low = min of all swing_low prices               |
//+------------------------------------------------------------------+
void UpdateHTFRange()
{
   // Copy daily candles
   CandleData daily_candles[];
   ArrayResize(daily_candles, HTFLookback);
   
   MqlRates rates[];
   int copied = CopyRates(_Symbol, PERIOD_D1, 1, HTFLookback, rates);
   if(copied < 3) return;
   
   ArrayResize(daily_candles, copied);
   for(int i = 0; i < copied; i++)
   {
      daily_candles[i].time  = rates[i].time;
      daily_candles[i].open  = rates[i].open;
      daily_candles[i].high  = rates[i].high;
      daily_candles[i].low   = rates[i].low;
      daily_candles[i].close = rates[i].close;
   }
   
   // Detect swing points with HTF lookback (2)
   SwingPoint swings[];
   int swing_count = DetectSwingPoints(daily_candles, copied, HTFSwingLookback, swings);
   
   if(swing_count == 0) return;
   
   // Find max swing_high and min swing_low
   double max_high = -DBL_MAX;
   double min_low  = DBL_MAX;
   bool found_high = false, found_low = false;
   
   for(int i = 0; i < swing_count; i++)
   {
      if(swings[i].is_high)
      {
         if(swings[i].price > max_high) max_high = swings[i].price;
         found_high = true;
      }
      else
      {
         if(swings[i].price < min_low) min_low = swings[i].price;
         found_low = true;
      }
   }
   
   if(found_high && found_low)
   {
      g_htf_swing_high  = max_high;
      g_htf_swing_low   = min_low;
      g_htf_range_valid = true;
   }
}

//+------------------------------------------------------------------+
//| Place Limit Order                                                  |
//| Corresponds to: backtester.py trade execution via OrderSend       |
//|                                                                    |
//| BUY_LIMIT or SELL_LIMIT at entry_price with SL and TP            |
//| Comment format: "ICT_<kill_zone_name>"                            |
//+------------------------------------------------------------------+
bool PlaceLimitOrder(const EntrySignal &signal)
{
   double volume = CalculatePositionSize(AccountInfoDouble(ACCOUNT_BALANCE),
                                          signal.entry_price, signal.stop_loss);
   if(volume <= 0.0)
      return false; // Position too small
   
   MqlTradeRequest request;
   MqlTradeResult  result;
   ZeroMemory(request);
   ZeroMemory(result);
   
   request.action   = TRADE_ACTION_PENDING;
   request.symbol   = _Symbol;
   request.volume   = volume;
   request.price    = NormalizeDouble(signal.entry_price, _Digits);
   request.sl       = NormalizeDouble(signal.stop_loss, _Digits);
   request.tp       = NormalizeDouble(signal.take_profit, _Digits);
   request.magic    = 20240101; // Magic number for ICT Bot
   request.comment  = "ICT_" + signal.kill_zone_name;
   request.type_time = ORDER_TIME_GTC;
   
   if(signal.direction == "long")
      request.type = ORDER_TYPE_BUY_LIMIT;
   else
      request.type = ORDER_TYPE_SELL_LIMIT;
   
   // Set deviation
   request.deviation = 10;
   
   // ORDER_FILLING_RETURN is always valid for pending orders (BUY_LIMIT/SELL_LIMIT)
   request.type_filling = ORDER_FILLING_RETURN;
   
   bool sent = OrderSend(request, result);
   
   if(sent && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
   {
      Print("ICT Bot: Order placed - ", signal.direction, " @ ", signal.entry_price,
            " SL: ", signal.stop_loss, " TP: ", signal.take_profit,
            " Vol: ", volume, " KZ: ", signal.kill_zone_name,
            " OTE: ", (signal.ote_confluence ? "Yes" : "No"),
            " OB: ", (signal.ob_confluence ? "Yes" : "No"));
      return true;
   }
   else
   {
      Print("ICT Bot: Order FAILED - retcode: ", result.retcode,
            " | comment: ", result.comment,
            " | dir: ", signal.direction,
            " | price: ", DoubleToString(signal.entry_price, _Digits),
            " | sl: ", DoubleToString(signal.stop_loss, _Digits),
            " | tp: ", DoubleToString(signal.take_profit, _Digits),
            " | vol: ", DoubleToString(volume, 2),
            " | filling: ", EnumToString(request.type_filling),
            " | bid: ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), _Digits),
            " | ask: ", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), _Digits));
      return false;
   }
}

//+------------------------------------------------------------------+
//| Check if we have any active positions or pending orders            |
//+------------------------------------------------------------------+
bool HasActiveTradeOrOrder()
{
   // Check positions
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol)
      {
         if(PositionGetInteger(POSITION_MAGIC) == 20240101)
            return true;
      }
   }
   
   // Check pending orders
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(OrderGetTicket(i)))
      {
         if(OrderGetString(ORDER_SYMBOL) == _Symbol
            && OrderGetInteger(ORDER_MAGIC) == 20240101)
            return true;
      }
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| Track daily PnL from closed trades                                 |
//+------------------------------------------------------------------+
void UpdateDailyPnL()
{
   MqlDateTime mdt;
   TimeCurrent();
   TimeToStruct(TimeCurrent(), mdt);
   int today = mdt.day_of_year;
   
   // Check if new day
   if(today != g_current_day)
   {
      g_current_day = today;
      g_daily_pnl = 0.0;
      g_day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
      
      // Update HTF range at start of each day
      // Corresponds to: backtester.py update_htf_range() call on day change
      UpdateHTFRange();
   }
   
   // Calculate today's realized PnL from deal history
   datetime day_start = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   
   // Select history for today
   HistorySelect(day_start, TimeCurrent());
   
   double today_pnl = 0.0;
   int deals = HistoryDealsTotal();
   for(int i = 0; i < deals; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket > 0)
      {
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) == _Symbol
            && HistoryDealGetInteger(ticket, DEAL_MAGIC) == 20240101)
         {
            today_pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT)
                       + HistoryDealGetDouble(ticket, DEAL_COMMISSION)
                       + HistoryDealGetDouble(ticket, DEAL_SWAP);
         }
      }
   }
   
   g_daily_pnl = today_pnl;
}

//+------------------------------------------------------------------+
//| Process New Candle - Main state machine logic                      |
//| Corresponds to: entry_model.py EntryModel.update()                |
//| and backtester.py main loop                                       |
//+------------------------------------------------------------------+
void ProcessNewCandle(const CandleData &candle, string kz_name)
{
   // Add candle to buffer
   AddCandleToBuffer(candle);
   
   // Cascade state machine: allow multiple state transitions on a single candle.
   // Previously used if/else-if which only advanced ONE state per candle. This caused
   // missed trades when MSS was detected on the last kill zone candle (no next candle
   // to check FVG before the kill zone reset).
   ENUM_ENTRY_STATE prev_state;
   do {
      prev_state = g_state;
      if(g_state == STATE_WAITING_FOR_SWEEP)
         CheckLiquiditySweep();
      if(g_state == STATE_WAITING_FOR_MSS)
         CheckMSS();
      if(g_state == STATE_WAITING_FOR_FVG)
         CheckFVG();
   } while(g_state != prev_state && g_state != STATE_READY_TO_ENTER);
   
   // Check if ready to enter
   if(g_state == STATE_READY_TO_ENTER)
   {
      EntrySignal signal;
      signal.valid = false;
      
      if(GenerateEntrySignal(signal, kz_name))
      {
         if(signal.valid)
         {
            if(DebugMode)
               Print("ICT Debug: [SIGNAL] Entry signal generated",
                     " | Dir=", signal.direction,
                     " | Entry=", DoubleToString(signal.entry_price, _Digits),
                     " | SL=", DoubleToString(signal.stop_loss, _Digits),
                     " | TP=", DoubleToString(signal.take_profit, _Digits),
                     " | R:R=", DoubleToString(signal.risk_reward, 2),
                     " | KZ=", kz_name,
                     " | OTE=", (signal.ote_confluence ? "Yes" : "No"),
                     " | OB=", (signal.ob_confluence ? "Yes" : "No"));
            
            PlaceLimitOrder(signal);
            
            // BUG 3 FIX: Mark that we have an active trade immediately after
            // placing the order. Without this, the EA would continue looking for
            // new entries on subsequent candles until HasActiveTradeOrOrder()
            // detected the pending order on the next tick.
            g_has_active_trade = true;
         }
      }
      else
      {
         if(DebugMode)
            Print("ICT Debug: [REJECTED] Signal generation returned false (P/D filter or invalid state)",
                  " | KZ=", kz_name);
      }
      
      // Reset after entry attempt (regardless of success)
      // Corresponds to: backtester.py entry_model.reset() after signal
      ResetEntryModel();
   }
}

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//| Corresponds to: main.py initialization                            |
//+------------------------------------------------------------------+
int OnInit()
{
   // Validate symbol
   if(!SymbolInfoInteger(_Symbol, SYMBOL_EXIST))
   {
      Print("ICT Bot: Symbol ", _Symbol, " does not exist!");
      return INIT_FAILED;
   }
   
   // Initialize state
   ResetEntryModel();
   g_last_bar_time = 0;
   g_bar_counter = 0;
   g_daily_pnl = 0.0;
   g_current_day = 0;
   g_day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_htf_range_valid = false;
   g_has_active_trade = false;
   
   // Set timer for 1-second polling to detect new bars
   // Note: EventSetTimer may not fire in Strategy Tester, but OnTick is always
   // called on each tick in the tester, so CheckForNewBar() will be invoked
   // regardless. The timer is a fallback for live trading with illiquid symbols.
   if(!MQLInfoInteger(MQL_TESTER))
      EventSetTimer(1);
   else
      Print("ICT Bot: Running in Strategy Tester - timer disabled, using OnTick only");
   
   // Initial HTF range update
   UpdateHTFRange();
   
   // Log initialization details including timezone info
   int broker_offset_sec = GetBrokerUTCOffsetSeconds();
   Print("ICT Bot: ========================================");
   Print("ICT Bot: Initialized on ", _Symbol);
   Print("ICT Bot: Risk=", RiskPercent * 100, "%, MaxDailyLoss=", MaxDailyLoss * 100, "%");
   Print("ICT Bot: SwingLookback=", SwingLookback, ", EqualLevelTol=", EqualLevelTolerance,
         ", MinSweep=", MinSweepPips, ", MaxBuffer=", MaxBufferSize);
   Print("ICT Bot: Timezone Config:");
   Print("ICT Bot:   ServerUTCOffset input=", ServerUTCOffset,
         " (", (ServerUTCOffset == -1 ? "AUTO-DETECT" : "MANUAL"), ")");
   Print("ICT Bot:   Detected broker offset=", broker_offset_sec/3600, " hours (",
         broker_offset_sec, " seconds)");
   Print("ICT Bot:   TimeGMTOffset()=", (int)TimeGMTOffset(), " seconds");
   Print("ICT Bot:   MQL_TESTER=", (MQLInfoInteger(MQL_TESTER) ? "YES" : "NO"));
   Print("ICT Bot:   Current server time=", TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES));
   
   // Show what ET time is right now for verification
   int et_h, et_m;
   ServerTimeToET(TimeCurrent(), et_h, et_m);
   Print("ICT Bot:   Current ET time=", StringFormat("%02d:%02d", et_h, et_m));
   
   string current_kz = GetActiveKillZone(TimeCurrent());
   Print("ICT Bot:   Current kill zone=", (current_kz == "" ? "NONE" : current_kz));
   Print("ICT Bot:   DebugMode=", (DebugMode ? "ON" : "OFF"));
   Print("ICT Bot:   HTF Range Valid=", (g_htf_range_valid ? "Yes" : "No"));
   if(g_htf_range_valid)
      Print("ICT Bot:   HTF High=", DoubleToString(g_htf_swing_high, _Digits),
            ", HTF Low=", DoubleToString(g_htf_swing_low, _Digits));
   
   // Print Kill Zone times in SERVER time for verification
   // ET -> UTC -> Server: server_time = ET_time - ET_offset + broker_offset
   // For June (EDT = UTC-4), with broker at UTC+3: offset from ET = +7 hours
   int et_offset_hours = GetETOffsetHours(TimeCurrent() - broker_offset_sec); // approximate
   int server_offset_from_et = broker_offset_sec / 3600 - et_offset_hours; // e.g. 3 - (-4) = 7
   Print("ICT Bot: ----------------------------------------");
   Print("ICT Bot: Kill Zone times in SERVER time (ET offset=", et_offset_hours,
         "h, server-ET shift=+", server_offset_from_et, "h):");
   // Asian: 20:00 - 00:00 ET
   Print("ICT Bot:   Asian  : server ",
         StringFormat("%02d:%02d", (20 + server_offset_from_et) % 24, 0), " - ",
         StringFormat("%02d:%02d", (0 + server_offset_from_et) % 24, 0),
         " (ET 20:00-00:00)");
   // London: 02:00 - 05:00 ET
   Print("ICT Bot:   London : server ",
         StringFormat("%02d:%02d", (2 + server_offset_from_et) % 24, 0), " - ",
         StringFormat("%02d:%02d", (5 + server_offset_from_et) % 24, 0),
         " (ET 02:00-05:00)");
   // NY AM: 10:00 - 11:00 ET
   Print("ICT Bot:   NY AM  : server ",
         StringFormat("%02d:%02d", (10 + server_offset_from_et) % 24, 0), " - ",
         StringFormat("%02d:%02d", (11 + server_offset_from_et) % 24, 0),
         " (ET 10:00-11:00)");
   // NY PM: 13:30 - 16:00 ET
   Print("ICT Bot:   NY PM  : server ",
         StringFormat("%02d:%02d", (13 + server_offset_from_et) % 24, 30), " - ",
         StringFormat("%02d:%02d", (16 + server_offset_from_et) % 24, 0),
         " (ET 13:30-16:00)");
   Print("ICT Bot: ----------------------------------------");
   Print("ICT Bot: NOTE: If server times look wrong, adjust ServerUTCOffset input.");
   Print("ICT Bot: ========================================");
   
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                    |
//| Corresponds to: cleanup on exit                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("ICT Bot: Deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Timer function - poll for new M1 bars                              |
//| This acts as a fallback when OnTick is not called frequently       |
//+------------------------------------------------------------------+
void OnTimer()
{
   CheckForNewBar();
}

//+------------------------------------------------------------------+
//| Tick function - primary event handler                               |
//| Corresponds to: backtester.py main loop iteration                 |
//+------------------------------------------------------------------+
void OnTick()
{
   CheckForNewBar();
}

//+------------------------------------------------------------------+
//| Check for new M1 bar and process it                                |
//| Main loop logic from backtester.py                                |
//+------------------------------------------------------------------+
void CheckForNewBar()
{
   // Get the time of the current (forming) M1 bar
   datetime current_bar_time = iTime(_Symbol, PERIOD_M1, 0);
   
   // Only process when a new bar forms (previous bar is complete)
   if(current_bar_time == g_last_bar_time)
      return;
   
   // If first run, just set the time and return
   if(g_last_bar_time == 0)
   {
      g_last_bar_time = current_bar_time;
      if(DebugMode)
         Print("ICT Debug: First bar detected, initializing. ServerTime=",
               TimeToString(current_bar_time, TIME_DATE|TIME_MINUTES),
               " | BrokerOffset=", GetBrokerUTCOffsetSeconds()/3600, "h");
      return;
   }
   
   g_last_bar_time = current_bar_time;
   
   // Increment bar counter for first-100-bars verbose debug
   g_bar_counter++;
   
   // Get the COMPLETED bar (index 1 = previous bar)
   MqlRates rates[];
   if(CopyRates(_Symbol, PERIOD_M1, 1, 1, rates) != 1)
      return;
   
   CandleData candle;
   candle.time  = rates[0].time;
   candle.open  = rates[0].open;
   candle.high  = rates[0].high;
   candle.low   = rates[0].low;
   candle.close = rates[0].close;
   
   // Update daily PnL tracking
   UpdateDailyPnL();
   
   // Check if we already have an active trade/order
   g_has_active_trade = HasActiveTradeOrOrder();
   
   // Only look for new entries if no active trade
   // Corresponds to: backtester.py "if active_trade is None"
   if(g_has_active_trade)
   {
      if(g_bar_counter <= 100)
         Print("ICT Bar[", g_bar_counter, "]: SKIP (active trade/order)",
               " | ServerTime=", TimeToString(candle.time, TIME_DATE|TIME_MINUTES));
      return;
   }
   
   // Check kill zone
   // Corresponds to: backtester.py is_in_kill_zone() check
   string kz_name = GetActiveKillZone(candle.time);
   
   // Verbose debug for first 100 bars: show server time, ET time, kill zone, buffer, state
   if(g_bar_counter <= 100)
   {
      int dbg_et_h, dbg_et_m;
      ServerTimeToET(candle.time, dbg_et_h, dbg_et_m);
      Print("ICT Bar[", g_bar_counter, "]: ServerTime=", TimeToString(candle.time, TIME_DATE|TIME_MINUTES),
            " | ET=", StringFormat("%02d:%02d", dbg_et_h, dbg_et_m),
            " | KZ=", (kz_name == "" ? "NONE" : kz_name),
            " | Buffer=", g_buffer_count,
            " | State=", EnumToString(g_state),
            " | BrokerOffset=", GetBrokerUTCOffsetSeconds()/3600, "h");
   }
   
   if(kz_name == "")
   {
      // Not in any kill zone - reset
      // Corresponds to: backtester.py "else: entry_model.reset()"
      if(g_buffer_count > 0)
      {
         if(DebugMode)
         {
            int et_hour, et_minute;
            ServerTimeToET(candle.time, et_hour, et_minute);
            Print("ICT Debug: [RESET] Outside kill zone, resetting buffer",
                  " | ServerTime=", TimeToString(candle.time, TIME_DATE|TIME_MINUTES),
                  " | ET=", StringFormat("%02d:%02d", et_hour, et_minute),
                  " | BufferSize=", g_buffer_count,
                  " | State=", EnumToString(g_state));
         }
         ResetEntryModel();
      }
      g_previous_kill_zone = "";
      return;
   }
   
   // Cancel stale pending orders when transitioning to a DIFFERENT kill zone.
   // This prevents leftover limit orders from a prior session lingering, while
   // NOT cancelling orders placed within the SAME kill zone (which was the bug:
   // ResetEntryModel used to call CancelPendingOrders on every reset, including
   // immediately after PlaceLimitOrder).
   if(g_previous_kill_zone != "" && g_previous_kill_zone != kz_name)
   {
      if(DebugMode)
         Print("ICT Debug: [KZ TRANSITION] ", g_previous_kill_zone, " -> ", kz_name,
               " | Cancelling stale pending orders from prior kill zone");
      CancelPendingOrders();
   }
   g_previous_kill_zone = kz_name;
   
   // Check daily loss limit before processing
   // Corresponds to: backtester.py daily loss check
   if(IsDailyLossLimitReached())
   {
      if(DebugMode)
         Print("ICT Debug: [BLOCKED] Daily loss limit reached, skipping",
               " | DailyPnL=", DoubleToString(g_daily_pnl, 2),
               " | DayStartBalance=", DoubleToString(g_day_start_balance, 2));
      ResetEntryModel();
      return;
   }
   
   // Process the candle through the state machine
   ProcessNewCandle(candle, kz_name);
}

//+------------------------------------------------------------------+
//| Trade transaction handler - for tracking closed trades             |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   // Update daily PnL when a deal is added (trade closed)
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      UpdateDailyPnL();
   }
}
//+------------------------------------------------------------------+
