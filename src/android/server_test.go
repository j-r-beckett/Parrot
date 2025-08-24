package main

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
)


// Test that all webhook endpoints are registered
func TestWebhookEndpointsRegistered(t *testing.T) {
	cm := NewClientManager()
	smsClient := NewSMSGatewayClient("http://localhost:8080", "test", "test")
	router := SetupRouter("test", cm, smsClient)
	ts := httptest.NewServer(router)
	defer ts.Close()
	
	events := []string{"sms:received", "sms:sent", "sms:delivered", "sms:failed"}
	
	for _, event := range events {
		// Send empty JSON object (will fail parsing but that's ok for this test)
		resp, err := http.Post(ts.URL+"/webhook/"+event, "application/json", bytes.NewBufferString("{}"))
		if err != nil {
			t.Fatalf("Failed to make request to %s: %v", event, err)
		}
		resp.Body.Close()
		
		// Should not be 404 (endpoint exists)
		if resp.StatusCode == http.StatusNotFound {
			t.Errorf("Webhook endpoint /webhook/%s not registered", event)
		}
	}
}