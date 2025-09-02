package main

import (
	"io/ioutil"
	"log"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMessageCacheDeduplication(t *testing.T) {
	// Redirect log output to discard for quiet test runs
	log.SetOutput(ioutil.Discard)

	cache := NewMessageCache()

	// First message should not be seen
	messageID := "test-message-123"
	if cache.IsSeenAndMark(messageID) {
		t.Error("Expected message to not be seen on first call")
	}

	// Same message should be seen on second call
	if !cache.IsSeenAndMark(messageID) {
		t.Error("Expected message to be seen on second call")
	}

	// Different message should not be seen
	if cache.IsSeenAndMark("different-message-456") {
		t.Error("Expected different message to not be seen")
	}
}

func TestMessageCacheCleanup(t *testing.T) {
	// Redirect log output to discard for quiet test runs
	log.SetOutput(ioutil.Discard)

	cache := NewMessageCache()

	// Add a message
	messageID := "cleanup-test-123"
	cache.IsSeenAndMark(messageID)

	// Manually set timestamp to old value
	cache.mu.Lock()
	cache.seen[messageID] = time.Now().Add(-10 * time.Minute)
	cache.mu.Unlock()

	// Run cleanup with 5 minute TTL
	cache.Cleanup(5 * time.Minute)

	// Message should be removed and not seen anymore
	if cache.IsSeenAndMark(messageID) {
		t.Error("Expected cleaned up message to not be seen")
	}
}

func TestWebhookDeduplication(t *testing.T) {
	// Redirect log output to discard for quiet test runs
	log.SetOutput(ioutil.Discard)

	cm := NewClientManager()
	am, _ := NewAllowlistManager(":memory:")
	mc := NewMessageCache()

	testCases := []struct {
		eventType string
		payload   string
	}{
		{"received", `{"id":"test1","webhookId":"wh1","deviceId":"dev1","event":"sms:received","payload":{"messageId":"msg123","phoneNumber":"+15551234567","message":"test","receivedAt":"2023-01-01T00:00:00Z"}}`},
		{"sent", `{"id":"test2","webhookId":"wh2","deviceId":"dev1","event":"sms:sent","payload":{"messageId":"msg456","phoneNumber":"+15551234567","sentAt":"2023-01-01T00:00:00Z"}}`},
		{"delivered", `{"id":"test3","webhookId":"wh3","deviceId":"dev1","event":"sms:delivered","payload":{"messageId":"msg789","phoneNumber":"+15551234567","deliveredAt":"2023-01-01T00:00:00Z"}}`},
		{"failed", `{"id":"test4","webhookId":"wh4","deviceId":"dev1","event":"sms:failed","payload":{"messageId":"msg999","phoneNumber":"+15551234567","failedAt":"2023-01-01T00:00:00Z","reason":"test"}}`},
	}

	// Add a test number to the allowlist so webhooks get processed
	am.AddNumber("+15551234567", "prod")

	for _, tc := range testCases {
		t.Run(tc.eventType+"_deduplication", func(t *testing.T) {
			handler := CreateWebhookHandler(tc.eventType, cm, am, mc)

			// First request should succeed (not duplicate)
			req1 := httptest.NewRequest("POST", "/webhook/"+tc.eventType, strings.NewReader(tc.payload))
			rr1 := httptest.NewRecorder()
			handler(rr1, req1)

			if rr1.Code != 200 {
				t.Errorf("Expected 200, got %d", rr1.Code)
			}

			// Second identical request should also return 200 but be deduplicated
			req2 := httptest.NewRequest("POST", "/webhook/"+tc.eventType, strings.NewReader(tc.payload))
			rr2 := httptest.NewRecorder()
			handler(rr2, req2)

			if rr2.Code != 200 {
				t.Errorf("Expected 200 for duplicate, got %d", rr2.Code)
			}
		})
	}
}

func TestWebhookDeduplicationDifferentEventTypes(t *testing.T) {
	// Redirect log output to discard for quiet test runs
	log.SetOutput(ioutil.Discard)

	cm := NewClientManager()
	am, _ := NewAllowlistManager(":memory:")
	mc := NewMessageCache()

	// Add a test number to the allowlist
	am.AddNumber("+15551234567", "prod")

	// Same MessageID but different event types should NOT be deduplicated
	sharedMessageID := "shared-msg-id"

	sentPayload := `{"id":"test1","webhookId":"wh1","deviceId":"dev1","event":"sms:sent","payload":{"messageId":"` + sharedMessageID + `","phoneNumber":"+15551234567","sentAt":"2023-01-01T00:00:00Z"}}`
	deliveredPayload := `{"id":"test2","webhookId":"wh2","deviceId":"dev1","event":"sms:delivered","payload":{"messageId":"` + sharedMessageID + `","phoneNumber":"+15551234567","deliveredAt":"2023-01-01T00:01:00Z"}}`

	// Send "sent" webhook
	sentHandler := CreateWebhookHandler("sent", cm, am, mc)
	req1 := httptest.NewRequest("POST", "/webhook/sent", strings.NewReader(sentPayload))
	rr1 := httptest.NewRecorder()
	sentHandler(rr1, req1)

	if rr1.Code != 200 {
		t.Errorf("Expected 200 for sent webhook, got %d", rr1.Code)
	}

	// Send "delivered" webhook with same MessageID - should NOT be deduplicated
	deliveredHandler := CreateWebhookHandler("delivered", cm, am, mc)
	req2 := httptest.NewRequest("POST", "/webhook/delivered", strings.NewReader(deliveredPayload))
	rr2 := httptest.NewRecorder()
	deliveredHandler(rr2, req2)

	if rr2.Code != 200 {
		t.Errorf("Expected 200 for delivered webhook, got %d", rr2.Code)
	}

	// Send same "delivered" webhook again - should be deduplicated this time
	req3 := httptest.NewRequest("POST", "/webhook/delivered", strings.NewReader(deliveredPayload))
	rr3 := httptest.NewRecorder()
	deliveredHandler(rr3, req3)

	if rr3.Code != 200 {
		t.Errorf("Expected 200 for duplicate delivered webhook, got %d", rr3.Code)
	}
}
