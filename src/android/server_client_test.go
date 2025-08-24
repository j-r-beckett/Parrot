package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRegisterEndpoint(t *testing.T) {
	cm := NewClientManager()
	smsClient := NewSMSGatewayClient("http://localhost:8080", "test", "test")
	router := SetupRouter("test", cm, smsClient)
	
	tests := []struct {
		name       string
		payload    interface{}
		wantStatus int
	}{
		{
			name: "valid registration",
			payload: RegisterRequest{
				ID:           "client1",
				WebhookURL:   "http://example.com/webhook",
				SmsReceived:  true,
				SmsSent:      false,
				SmsDelivered: true,
				SmsFailed:    false,
			},
			wantStatus: http.StatusOK,
		},
		{
			name: "missing ID",
			payload: RegisterRequest{
				WebhookURL: "http://example.com/webhook",
			},
			wantStatus: http.StatusBadRequest,
		},
		{
			name: "ID too long",
			payload: RegisterRequest{
				ID:         string(make([]byte, 129)), // 129 chars
				WebhookURL: "http://example.com/webhook",
			},
			wantStatus: http.StatusBadRequest,
		},
		{
			name: "missing webhook URL",
			payload: RegisterRequest{
				ID: "client1",
			},
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "invalid JSON",
			payload:    "not json",
			wantStatus: http.StatusBadRequest,
		},
	}
	
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var body []byte
			if str, ok := tt.payload.(string); ok {
				body = []byte(str)
			} else {
				body, _ = json.Marshal(tt.payload)
			}
			
			req := httptest.NewRequest("POST", "/register", bytes.NewBuffer(body))
			req.Header.Set("Content-Type", "application/json")
			rr := httptest.NewRecorder()
			
			router.ServeHTTP(rr, req)
			
			if status := rr.Code; status != tt.wantStatus {
				t.Errorf("handler returned wrong status code: got %v want %v", status, tt.wantStatus)
			}
			
			// For successful registration, verify client was stored
			if tt.wantStatus == http.StatusOK {
				if reqData, ok := tt.payload.(RegisterRequest); ok {
					client, exists := cm.Get(reqData.ID)
					if !exists {
						t.Error("Client was not registered")
					}
					if client.WebhookURL != reqData.WebhookURL {
						t.Errorf("Webhook URL mismatch: got %v want %v", client.WebhookURL, reqData.WebhookURL)
					}
				}
			}
		})
	}
}

func TestClientsEndpoint(t *testing.T) {
	cm := NewClientManager()
	smsClient := NewSMSGatewayClient("http://localhost:8080", "test", "test")
	router := SetupRouter("test", cm, smsClient)
	
	// Register some clients
	cm.Register("client1", &Client{ID: "client1", WebhookURL: "http://example1.com"})
	cm.Register("client2", &Client{ID: "client2", WebhookURL: "http://example2.com"})
	
	req := httptest.NewRequest("GET", "/clients", nil)
	rr := httptest.NewRecorder()
	
	router.ServeHTTP(rr, req)
	
	if status := rr.Code; status != http.StatusOK {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusOK)
	}
	
	var clients []*Client
	if err := json.NewDecoder(rr.Body).Decode(&clients); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}
	
	if len(clients) != 2 {
		t.Errorf("Expected 2 clients, got %d", len(clients))
	}
	
	// Check both clients exist with correct URLs
	foundClient1 := false
	foundClient2 := false
	for _, client := range clients {
		if client.ID == "client1" && client.WebhookURL == "http://example1.com" {
			foundClient1 = true
		}
		if client.ID == "client2" && client.WebhookURL == "http://example2.com" {
			foundClient2 = true
		}
	}
	if !foundClient1 {
		t.Error("Client1 not found or has wrong webhook URL")
	}
	if !foundClient2 {
		t.Error("Client2 not found or has wrong webhook URL")
	}
}