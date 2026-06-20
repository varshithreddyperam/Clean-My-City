const dbHelper = require('./database');

class UrbanSimulator {
  constructor(broadcastEvent) {
    this.broadcastEvent = broadcastEvent;
    this.isRunning = false;
    this.intervalId = null;
    this.ratePerMinute = 120; // Default: 2 submissions per second
    this.simulatedUsers = [
      "alpha_cleaner", "nature_lover", "recycle_queen", "city_hero", 
      "green_knight", "street_sweeper", "eco_pathfinder", "urban_guardian",
      "waste_watcher", "clean_air_advocate", "sust_champion", "zero_waste_warrior"
    ];
    this.cityCenter = { lat: 40.7128, lng: -74.0060 }; // NYC area center
  }

  start(rate) {
    if (this.isRunning) this.stop();
    this.isRunning = true;
    this.ratePerMinute = rate;
    
    // Calculate interval in ms (e.g., 120 per minute = 1 transaction every 500ms)
    const intervalMs = (60 * 1000) / this.ratePerMinute;
    
    this.intervalId = setInterval(() => {
      this.generateSimulatedReport();
    }, intervalMs);

    console.log(`Urban simulator started at ${this.ratePerMinute} reports/minute.`);
  }

  stop() {
    this.isRunning = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    console.log("Urban simulator stopped.");
  }

  updateRate(rate) {
    this.ratePerMinute = rate;
    if (this.isRunning) {
      this.start(rate);
    }
  }

  generateSimulatedReport() {
    const randomUser = this.simulatedUsers[Math.floor(Math.random() * this.simulatedUsers.length)];
    
    // Generate coordinate within ~2km radius of center
    const latOffset = (Math.random() - 0.5) * 0.04;
    const lngOffset = (Math.random() - 0.5) * 0.04;
    const coordinates = {
      lat: Number((this.cityCenter.lat + latOffset).toFixed(6)),
      lng: Number((this.cityCenter.lng + lngOffset).toFixed(6))
    };

    // Determine disposal scenario:
    // 55% Recyclable, 30% Non-Recyclable, 10% Littered, 5% Spoof (duplicate)
    const roll = Math.random();
    let classification = 'recyclable';
    let isSpoof = false;

    if (roll > 0.95) {
      isSpoof = true;
    } else if (roll > 0.85) {
      classification = 'littered';
    } else if (roll > 0.55) {
      classification = 'non-recyclable';
    }

    let imageHash = `hash_${Math.floor(Math.random() * 1000000)}`;
    if (isSpoof) {
      imageHash = "spoof_dup_hash_9999";
    }

    // Call database submit
    const result = dbHelper.submitDisposal(randomUser, imageHash, classification, coordinates);

    if (!result.success) {
      // Cooldown block or spoof reject
      this.broadcastEvent('simulator-event', {
        type: 'rejected_instant',
        username: randomUser,
        classification,
        coordinates,
        message: result.error,
        transaction: result.transaction,
        timestamp: Date.now()
      });
      return;
    }

    const transaction = result.transaction;
    
    // Emit initial submission event (Submission -> Verification Pending)
    this.broadcastEvent('simulator-event', {
      type: 'submission',
      username: randomUser,
      classification,
      coordinates,
      transaction,
      timestamp: Date.now()
    });

    // Add to verification queue. We will resolve it in 1 to 2.5 seconds to simulate pipeline delay
    const delay = 1000 + Math.random() * 1500;
    setTimeout(() => {
      const approve = classification !== 'littered';
      const finalResult = dbHelper.finalizeVerification(transaction.id, approve);
      
      if (finalResult) {
        this.broadcastEvent('simulator-event', {
          type: 'verification_completed',
          transaction: finalResult.transaction,
          user: finalResult.user,
          timestamp: Date.now()
        });
      }
    }, delay);
  }

  // Get active queue statistics
  getStats() {
    const ledger = dbHelper.getLedger();
    const totalTransactions = ledger.length;
    const pendingTransactions = ledger.filter(item => item.status === 'Verification Pending').length;
    const awardedTransactions = ledger.filter(item => item.status === 'Points Awarded').length;
    const rejectedTransactions = ledger.filter(item => item.status === 'Rejected').length;
    const spoofTransactions = ledger.filter(item => item.status === 'Spoof Rejected').length;

    // Simulate CPU load based on throughput rate & pending queue
    const baseCpu = 5; // Idle load
    const rateLoad = (this.ratePerMinute / 10); // 0.1% CPU per report/min
    const queueLoad = pendingTransactions * 2.5; // 2.5% CPU per pending task
    const cpuLoad = Math.min(Math.round(baseCpu + rateLoad + queueLoad), 99);

    return {
      isRunning: this.isRunning,
      ratePerMinute: this.ratePerMinute,
      totalTransactions,
      pendingTransactions,
      awardedTransactions,
      rejectedTransactions,
      spoofTransactions,
      cpuLoad
    };
  }
}

module.exports = UrbanSimulator;
