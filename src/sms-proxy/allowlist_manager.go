package main

import (
	"database/sql"
	"fmt"
	"log"
	"sync"

	_ "modernc.org/sqlite"
)

// AllowlistManager manages the collection of allowed phone numbers and their ring assignments
type AllowlistManager struct {
	db      *sql.DB
	numbers map[string]string // phone_number -> ring
	mu      sync.RWMutex
	dbPath  string
}

// NewAllowlistManager creates a new allowlist number manager
func NewAllowlistManager(dbPath string) (*AllowlistManager, error) {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %v", err)
	}

	// Test the connection
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %v", err)
	}

	manager := &AllowlistManager{
		db:      db,
		numbers: make(map[string]string),
		dbPath:  dbPath,
	}

	// Initialize database schema
	if err := manager.initDB(); err != nil {
		return nil, fmt.Errorf("failed to initialize database: %v", err)
	}

	// Load existing numbers from database
	if err := manager.loadNumbers(); err != nil {
		return nil, fmt.Errorf("failed to load numbers: %v", err)
	}

	return manager, nil
}

// initDB creates the database schema if it doesn't exist
func (am *AllowlistManager) initDB() error {
	query := `
		CREATE TABLE IF NOT EXISTS allowed_numbers (
			phone_number TEXT PRIMARY KEY,
			ring TEXT NOT NULL
		);
	`
	_, err := am.db.Exec(query)
	return err
}

// loadNumbers loads all allowed numbers from the database into memory
func (am *AllowlistManager) loadNumbers() error {
	am.mu.Lock()
	defer am.mu.Unlock()

	rows, err := am.db.Query("SELECT phone_number, ring FROM allowed_numbers")
	if err != nil {
		return err
	}
	defer rows.Close()

	// Clear existing in-memory numbers
	am.numbers = make(map[string]string)

	// Load from database
	for rows.Next() {
		var phoneNumber, ring string
		if err := rows.Scan(&phoneNumber, &ring); err != nil {
			return err
		}
		am.numbers[phoneNumber] = ring
	}

	log.Printf("Loaded %d allowed numbers from database", len(am.numbers))
	return rows.Err()
}

// AddNumber adds a phone number to the allowlist with specified ring
func (am *AllowlistManager) AddNumber(phoneNumber, ring string) error {
	am.mu.Lock()
	defer am.mu.Unlock()

	// Check if number already exists
	if existingRing, exists := am.numbers[phoneNumber]; exists {
		if existingRing == ring {
			return fmt.Errorf("number %s is already assigned to ring %s", phoneNumber, ring)
		}
		return fmt.Errorf("number %s is already assigned to ring %s, cannot reassign to %s", phoneNumber, existingRing, ring)
	}

	// Add to database
	_, err := am.db.Exec("INSERT INTO allowed_numbers (phone_number, ring) VALUES (?, ?)", phoneNumber, ring)
	if err != nil {
		return err
	}

	// Add to in-memory map
	am.numbers[phoneNumber] = ring
	log.Printf("Added allowlist number: %s -> %s", phoneNumber, ring)
	return nil
}

// RemoveNumber removes a phone number from the allowlist
func (am *AllowlistManager) RemoveNumber(phoneNumber string) error {
	am.mu.Lock()
	defer am.mu.Unlock()

	// Remove from database
	_, err := am.db.Exec("DELETE FROM allowed_numbers WHERE phone_number = ?", phoneNumber)
	if err != nil {
		return err
	}

	// Remove from in-memory map
	delete(am.numbers, phoneNumber)
	log.Printf("Removed allowlist number: %s", phoneNumber)
	return nil
}

// GetRing returns the ring for a phone number, or empty string if not allowed
func (am *AllowlistManager) GetRing(phoneNumber string) string {
	am.mu.RLock()
	defer am.mu.RUnlock()
	return am.numbers[phoneNumber]
}

// IsAllowed checks if a phone number is in the allowlist
func (am *AllowlistManager) IsAllowed(phoneNumber string) bool {
	am.mu.RLock()
	defer am.mu.RUnlock()
	_, exists := am.numbers[phoneNumber]
	return exists
}

// GetAllNumbers returns all allowed numbers with their ring assignments
func (am *AllowlistManager) GetAllNumbers() map[string]string {
	am.mu.RLock()
	defer am.mu.RUnlock()

	// Return a copy to avoid race conditions
	result := make(map[string]string, len(am.numbers))
	for number, ring := range am.numbers {
		result[number] = ring
	}
	return result
}

// GetNumbersForRing returns all numbers assigned to a specific ring
func (am *AllowlistManager) GetNumbersForRing(ring string) []string {
	am.mu.RLock()
	defer am.mu.RUnlock()

	var numbers []string
	for number, assignedRing := range am.numbers {
		if assignedRing == ring {
			numbers = append(numbers, number)
		}
	}
	return numbers
}

// Close closes the database connection
func (am *AllowlistManager) Close() error {
	if am.db != nil {
		return am.db.Close()
	}
	return nil
}
