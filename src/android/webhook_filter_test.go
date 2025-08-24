package main

import (
	"testing"
)

func TestFilterByEvent(t *testing.T) {
	clients := []*Client{
		{ID: "1", SmsReceived: true, SmsSent: false, SmsDelivered: true, SmsFailed: false},
		{ID: "2", SmsReceived: false, SmsSent: true, SmsDelivered: false, SmsFailed: true},
		{ID: "3", SmsReceived: true, SmsSent: true, SmsDelivered: true, SmsFailed: true},
	}
	
	tests := []struct {
		name      string
		eventType string
		wantIDs   []string
	}{
		{
			name:      "filter sms:received",
			eventType: "sms:received",
			wantIDs:   []string{"1", "3"},
		},
		{
			name:      "filter sms:sent",
			eventType: "sms:sent",
			wantIDs:   []string{"2", "3"},
		},
		{
			name:      "filter sms:delivered",
			eventType: "sms:delivered",
			wantIDs:   []string{"1", "3"},
		},
		{
			name:      "filter sms:failed",
			eventType: "sms:failed",
			wantIDs:   []string{"2", "3"},
		},
	}
	
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			filtered := FilterByEvent(clients, tt.eventType)
			
			if len(filtered) != len(tt.wantIDs) {
				t.Errorf("Expected %d clients, got %d", len(tt.wantIDs), len(filtered))
			}
			
			// Check that we got the right clients
			gotIDs := make(map[string]bool)
			for _, c := range filtered {
				gotIDs[c.ID] = true
			}
			
			for _, wantID := range tt.wantIDs {
				if !gotIDs[wantID] {
					t.Errorf("Expected client %s to be included", wantID)
				}
			}
		})
	}
}

func TestFilterByNumberIncludes(t *testing.T) {
	clients := []*Client{
		{ID: "1", IncludeReceivedFrom: []string{"+15551234567", "+15557654321"}},
		{ID: "2", IncludeReceivedFrom: []string{"+15551234567"}},
		{ID: "3", IncludeReceivedFrom: []string{}}, // No include list
		{ID: "4", IncludeReceivedFrom: []string{"+15559999999"}},
	}
	
	tests := []struct {
		name        string
		phoneNumber string
		wantIDs     []string
	}{
		{
			name:        "number in some include lists",
			phoneNumber: "+15551234567",
			wantIDs:     []string{"1", "2", "3"}, // 3 has no list so passes through
		},
		{
			name:        "number not in any include list",
			phoneNumber: "+15550000000",
			wantIDs:     []string{"3"}, // Only 3 passes (no include list)
		},
		{
			name:        "empty phone number",
			phoneNumber: "",
			wantIDs:     []string{"3"}, // Only 3 passes (no include list)
		},
	}
	
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			filtered := FilterByNumberIncludes(clients, tt.phoneNumber)
			
			if len(filtered) != len(tt.wantIDs) {
				t.Errorf("Expected %d clients, got %d", len(tt.wantIDs), len(filtered))
			}
			
			gotIDs := make(map[string]bool)
			for _, c := range filtered {
				gotIDs[c.ID] = true
			}
			
			for _, wantID := range tt.wantIDs {
				if !gotIDs[wantID] {
					t.Errorf("Expected client %s to be included", wantID)
				}
			}
		})
	}
}

func TestFilterByNumberExcludes(t *testing.T) {
	clients := []*Client{
		{ID: "1", ExcludeReceivedFrom: []string{"+15551234567", "+15557654321"}},
		{ID: "2", ExcludeReceivedFrom: []string{"+15551234567"}},
		{ID: "3", ExcludeReceivedFrom: []string{}}, // No exclude list
		{ID: "4", ExcludeReceivedFrom: []string{"+15559999999"}},
	}
	
	tests := []struct {
		name        string
		phoneNumber string
		wantIDs     []string
	}{
		{
			name:        "number in some exclude lists",
			phoneNumber: "+15551234567",
			wantIDs:     []string{"3", "4"}, // 1 and 2 exclude this number
		},
		{
			name:        "number not in any exclude list",
			phoneNumber: "+15550000000",
			wantIDs:     []string{"1", "2", "3", "4"}, // All pass through
		},
		{
			name:        "empty phone number",
			phoneNumber: "",
			wantIDs:     []string{"1", "2", "3", "4"}, // Empty doesn't match any excludes
		},
	}
	
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			filtered := FilterByNumberExcludes(clients, tt.phoneNumber)
			
			if len(filtered) != len(tt.wantIDs) {
				t.Errorf("Expected %d clients, got %d", len(tt.wantIDs), len(filtered))
			}
			
			gotIDs := make(map[string]bool)
			for _, c := range filtered {
				gotIDs[c.ID] = true
			}
			
			for _, wantID := range tt.wantIDs {
				if !gotIDs[wantID] {
					t.Errorf("Expected client %s to be included", wantID)
				}
			}
		})
	}
}

func TestPhoneNumberValidation(t *testing.T) {
	validNumbers := []string{
		"+12064965136",
		"2064965136",
		"+15123662653",
		"5123662653",
		"+1234567890123", // 14 digits with +
		"1234567890",      // 10 digits
	}
	
	invalidNumbers := []string{
		"123456789",        // Too short (9 digits)
		"+123456789012345", // Too long (15 digits)
		"abc1234567890",    // Contains letters
		"+1-206-496-5136",  // Contains dashes
		"(206) 496-5136",   // Contains parens and spaces
		"",                 // Empty
	}
	
	for _, num := range validNumbers {
		if !phoneNumberRegex.MatchString(num) {
			t.Errorf("Expected %s to be valid", num)
		}
	}
	
	for _, num := range invalidNumbers {
		if phoneNumberRegex.MatchString(num) {
			t.Errorf("Expected %s to be invalid", num)
		}
	}
}

func TestCombinedFiltering(t *testing.T) {
	// Test that filters work together correctly
	clients := []*Client{
		{
			ID:                  "1",
			SmsReceived:         true,
			IncludeReceivedFrom: []string{"+15551234567"},
			ExcludeReceivedFrom: []string{},
		},
		{
			ID:                  "2",
			SmsReceived:         true,
			IncludeReceivedFrom: []string{},
			ExcludeReceivedFrom: []string{"+15551234567"},
		},
		{
			ID:                  "3",
			SmsReceived:         false, // Not subscribed to received
			IncludeReceivedFrom: []string{"+15551234567"},
			ExcludeReceivedFrom: []string{},
		},
		{
			ID:                  "4",
			SmsReceived:         true,
			IncludeReceivedFrom: []string{},
			ExcludeReceivedFrom: []string{},
		},
	}
	
	// First filter by event
	filtered := FilterByEvent(clients, "sms:received")
	// Should have clients 1, 2, 4 (not 3 because not subscribed)
	if len(filtered) != 3 {
		t.Errorf("Expected 3 clients after event filter, got %d", len(filtered))
	}
	
	// Then filter by includes
	filtered = FilterByNumberIncludes(filtered, "+15551234567")
	// Should have clients 1 (in include list), 2 and 4 (no include list)
	if len(filtered) != 3 {
		t.Errorf("Expected 3 clients after include filter, got %d", len(filtered))
	}
	
	// Finally filter by excludes
	filtered = FilterByNumberExcludes(filtered, "+15551234567")
	// Should have clients 1 and 4 (client 2 excludes this number)
	if len(filtered) != 2 {
		t.Errorf("Expected 2 clients after exclude filter, got %d", len(filtered))
	}
	
	// Check we have the right clients
	gotIDs := make(map[string]bool)
	for _, c := range filtered {
		gotIDs[c.ID] = true
	}
	
	if !gotIDs["1"] || !gotIDs["4"] {
		t.Errorf("Expected clients 1 and 4, got %v", gotIDs)
	}
}